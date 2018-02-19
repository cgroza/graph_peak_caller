from itertools import chain
from collections import defaultdict
import scipy.sparse.csgraph as csgraph
from scipy.sparse import csr_matrix
from .holes_analyzer import HolesAnalyzer
import numpy as np

"""
Logical stuff:
"""


class StubsFilter:
    def __init__(self, starts, fulls, ends, graph):
        self._graph = graph
        self._starts = starts
        self._fulls = fulls
        self._ends = ends

        self._starts_mask = np.ones_like(starts, dtype="bool")
        self._fulls_mask = np.ones_like(fulls, dtype="bool")
        self._ends_mask = np.ones_like(ends, dtype="bool")

        self.filter_start_stubs()
        self.filter_end_stubs()

        self.filtered_ends = self._ends[self._ends_mask]
        self.filtered_starts = self._starts[self._starts_mask]
        self.filtered_fulls = self._fulls[self._fulls_mask]

        self._pos_to_nodes = set(chain(self._fulls, self._ends))
        self._pos_from_nodes = set(chain(self._starts, self._fulls))

        self._full_starts = np.flatnonzero(self.find_sub_starts(self.filtered_fulls))
        self._end_starts = np.flatnonzero(self.find_sub_starts(self.filtered_ends))
        self._full_ends = np.flatnonzero(self.find_sub_ends(self.filtered_fulls))
        self._start_ends = np.flatnonzero(self.find_sub_ends(self.filtered_starts))

    def find_sub_starts(self, nodes):
        return np.array([not all(-adj in self._pos_from_nodes
                                 for adj in self._graph.reverse_adj_list[-node])
                         for node in nodes], dtype="bool")

    def find_sub_ends(self, nodes):
        return np.array([not all(adj in self._pos_to_nodes
                                 for adj in self._graph.adj_list[node])
                         for node in nodes], dtype="bool")

    def _get_start_filter(self, nodes):
        return np.array([bool(self._graph.reverse_adj_list[-node_id])
                         for node_id in nodes], dtype="bool")

    def _get_ends_filter(self, nodes):
        return np.array([bool(self._graph.adj_list[node_id])
                         for node_id in nodes], dtype="bool")

    def filter_start_stubs(self):
        """ Locate nodes that are start_nodes of graph"""
        self._fulls_mask &= self._get_start_filter(self._fulls)
        self._ends_mask &= self._get_start_filter(self._ends)

    def filter_end_stubs(self):
        self._starts_mask &= self._get_ends_filter(self._starts)
        self._fulls_mask &= self._get_ends_filter(self._fulls)


class LineGraph:
    def __init__(self, starts, full, ends, ob_graph):
        self.filtered = StubsFilter(starts[0], full[0], ends[0], ob_graph)
        self.full_size = full[1][self.filtered._fulls_mask]
        self.start_size = starts[1][self.filtered._starts_mask]
        self.end_size = ends[1][self.filtered._ends_mask]

        self.kept_starts = np.vstack((starts[0][~self.filtered._starts_mask],
                                      starts[1][~self.filtered._starts_mask]))
        self.kept_ends = np.vstack((ends[0][~self.filtered._ends_mask],
                                    ends[1][~self.filtered._ends_mask]))
        self.kept_fulls = full[0][~self.filtered._fulls_mask]

        self.full_nodes = self.filtered.filtered_fulls
        self.start_nodes = self.filtered.filtered_starts
        self.end_nodes = self.filtered.filtered_ends

        self._all_nodes = np.r_[self.start_nodes,
                                self.full_nodes,
                                self.end_nodes]

        self._all_sizes = np.r_[self.start_size,
                                self.full_size,
                                self.end_size]
        self.ob_graph = ob_graph

        self.n_starts = self.start_nodes.size
        self.n_ends = self.start_nodes.size
        self.n_nodes = self._all_nodes.size

        self._matrix = self.make_graph()

    def make_graph(self):
        n_starts = self.start_nodes.size
        n_ends = self.end_nodes.size
        to_nodes_dict = {node: n_starts+i for i, node in
                         enumerate(self._all_nodes[n_starts:])}
        self.end_stub = self._all_nodes.size
        from_nodes = []
        to_nodes = []
        sizes = []
        possible_to_nodes = set(list(self._all_nodes[n_starts:]))
        for i, node_id in enumerate(self._all_nodes[:-n_ends]):
            adj_nodes = self.ob_graph.adj_list[node_id]
            next_nodes = [to_nodes_dict[node] for node in
                          adj_nodes if node in possible_to_nodes]
            from_nodes.extend([i]*len(next_nodes))
            to_nodes.extend(next_nodes)
            sizes.extend([self._all_sizes[i]]*len(next_nodes))

        end_nodes = np.r_[self.filtered._start_ends,
                          n_starts + self.filtered._full_ends,
                          np.arange(self.n_nodes-n_ends, self.n_nodes)]

        to_nodes.extend([self.end_stub]*end_nodes.size)
        from_nodes.extend(list(end_nodes))
        sizes.extend(self._all_sizes[end_nodes])
        self.n_starts = n_starts
        self._graph_node_sizes = sizes
        return csr_matrix((np.array(sizes), (np.array(from_nodes),
                                             np.array(to_nodes))),
                          [self.end_stub+1, self.end_stub+1])

    def get_masked(self, mask):
        n_starts, n_ends = self.n_starts, self.n_ends
        starts = np.vstack((self._all_nodes[:n_starts][mask[:n_starts]],
                            self._all_sizes[:n_starts][mask[:n_starts]]))
        fulls = self._all_nodes[n_starts:-n_ends][mask[n_starts:-n_ends]]
        ends = np.vstack((self._all_nodes[-n_ends:][mask[-n_ends:]],
                          self._all_sizes[-n_ends:][mask[-n_ends:]]))
        starts = np.hstack((starts, self.kept_starts))
        ends = np.hstack((ends, self.kept_ends))
        print(fulls)
        print(self.kept_fulls)
        fulls = np.r_[fulls, self.kept_fulls]
        return starts, fulls, ends

    def filter_small(self, max_size):
        start_nodes = np.r_[np.arange(self.n_starts),
                            self.n_starts+self.filtered._full_starts,
                            self.n_nodes-self.n_ends+self.filtered._end_starts]
        shortest_paths = csgraph.shortest_path(self._matrix)
        to_dist = np.min(shortest_paths[start_nodes], axis=0)
        from_dist = shortest_paths[:, self.end_stub]
        return (to_dist+from_dist)[:-1] > max_size


class HolesCleaner:
    def __init__(self, graph, sparse_values, max_size):
        self._graph = graph
        self._node_indexes = graph.node_indexes
        self._sparse_values = sparse_values
        self._holes = self.get_holes()
        print(self._holes)
        self._node_ids = self.get_node_ids()
        self._max_size = max_size
        self._kept = []

    def get_holes(self):
        start_idx = 0
        if self._sparse_values.values[0] != 0:
            start_idx += 1
        end_idx = self._sparse_values.indices.size
        if self._sparse_values.values[-1] == 0:
            end_idx -= 1

        return self._sparse_values.indices[start_idx:end_idx].reshape(
            (end_idx-start_idx)//2, 2)

    def get_node_ids(self):
        node_ids = np.empty_like(self._holes)
        node_ids[:, 0] = np.digitize(self._holes[:, 0], self._node_indexes)
        node_ids[:, 1] = np.digitize(self._holes[:, 1], self._node_indexes, True)
        return node_ids

    def get_big_holes(self, internal_holes):
        return (internal_holes[:, 1]-internal_holes[0]) > self._max_size

    def _border_clean(self, full_mask, start_mask, end_mask, border_mask):
        full_starts = border_mask & start_mask
        full_ends = border_mask & end_mask
        start_mask -= full_starts
        end_mask -= full_starts
        return full_starts, full_ends

    def _handle_internal_holes(self, mask):
        holes = self._holes[mask]
        node_ids = self._node_ids[mask]
        is_start = holes[:, 0] == self._node_indexes[node_ids[:, 0]-1]
        true_internals = holes[~is_start]

    def _get_starts(self, pos, node_id):
        size = pos-self._node_indexes[node_id-1]
        return np.vstack((node_id, size))

    def _get_ends(self, pos, node_id):
        size = self._node_indexes[node_id]-pos
        return np.vstack((node_id, size))

    def _get_fulls(self, fulls):
        return np.vstack((
            fulls,
            self._node_indexes[fulls]-self._node_indexes[fulls-1]))

    def _handle_internal(self, internal_holes):
        keep = (internal_holes[:, 1]-internal_holes[:, 0]) >= self._max_size
        self._kept_internals = internal_holes[keep]

    def classify_holes(self, hole_starts, hole_ends, start_ids, end_ids, is_multinodes):
        is_starts = hole_starts == self._node_indexes[start_ids-1]
        is_ends = hole_ends == self._node_indexes[end_ids]
        full_start_filter = is_starts & (is_ends | is_multinodes)
        full_end_filter = is_ends & (is_multinodes)
        starts_filter = is_starts ^ full_start_filter
        ends_filter = is_ends ^ (is_starts | is_multinodes)
        return starts_filter, ends_filter, full_start_filter, full_end_filter

    def divide_on_nodes(self, holes, node_ids):
        multinodes = nodes_ids[:, 0] != node_ids[:, 1]

    def run(self):
        analyzer = HolesAnalyzer(
            self._holes, self._node_ids, self._node_indexes)
        analyzer.run()
        linegraph = LineGraph(analyzer.get_ends(), analyzer.get_fulls(),
                              analyzer.get_starts(), self._graph)
        mask = linegraph.filter_small(self._max_size)
        self._kept_borders = linegraph.get_masked(mask)
        self._handle_internal(analyzer._internal_holes)
        return(self.build_kept_holes())

    def build_kept_holes(self):
        starts, fulls, ends = self._kept_borders
        n_starts, n_fulls, n_ends = starts.shape[1], fulls.size, ends.shape[1]
        n_internals = self._kept_internals.shape[0]
        all_holes = np.empty((n_starts+n_fulls+n_ends+n_internals, 2),
                             dtype="int")
        all_holes[:n_starts, 0] = self._node_indexes[starts[0]]-starts[1]
        all_holes[:n_starts, 1] = self._node_indexes[starts[0]]
        n_border = n_starts+n_fulls+n_ends
        all_holes[n_starts:n_starts+n_fulls, 0] = self._node_indexes[fulls-1]
        all_holes[n_starts:n_starts+n_fulls, 1] = self._node_indexes[fulls]
        all_holes[n_starts+n_fulls:n_border, 0] = self._node_indexes[ends[0]-1]
        all_holes[n_starts+n_fulls:n_border, 1] = self._node_indexes[ends[0]-1] + ends[1]
        all_holes[n_border:] = self._kept_internals
        all_holes.sort(axis=0)
        print("#", all_holes)
        return all_holes

    def handle_border_holes(self, holes, node_ids):
        # node_offsets = self._node_indexes[node_ids]
        node_id_diffs = node_ids[:, 1]-node_ids[:, 0]
        full_nodes = (chain(range(i[0]+1, i[1])
                            for i in holes[node_id_diffs > 1]))
        full_nodes = [node for node in full_nodes if
                      self._graph.node_size(node) <= self._max_size]

        starts = np.vstack((holes[:, 0], self._node_indexes[node_ids[:, 1]+1]))
        ends = np.vstack((self._node_indexes[node_ids[:, 1]+1], holes[:, 1]))

    def find_border_holes(self):
        holes = self._holes.copy()
        holes[:, 1] += 1
        borders = np.digitize(self._graph.node_indexes, holes.ravel)
        border_holes = np.unique(borders)
        border_holes = border_holes[border_holes % 2 == 1]//2
        return border_holes


def test_holes_cleaner():
    import offsetbasedgraph as obg

    class S:
        indices = np.arange(0, 1000, 120)
        values = np.array([i % 2 for i in indices])

    class G:
        node_indexes = np.arange(0, 1001, 100)
        node_size = lambda x: 100

    graph = obg.Graph({i+1: obg.Block(100) for i in range(10)},
                      {i: [i+1] for i in range(0, 9)})
    graph.node_indexes = np.arange(0, 1001, 100)
    print(HolesCleaner(graph, S(), 20).run())

if __name__ == "__main__":
    test_holes_cleaner()

    exit()


    starts = [[1, 2, 3], [10, 100, 3]]
    fulls = [[11, 12, 13, 14, 15], [10, 20, 30, 1, 1]]
    ends = [[21, 22], [60, 1]]
    tmp = {
        1: [11, 12],
        11: [21],
        12: [21],
        13: [22]
    }
    nodes = {i: obg.Block(10) for i in range(5, 100)}
    graph = obg.GraphWithReversals(nodes, tmp)
    l = LineGraph(np.array(starts), np.array(fulls), np.array(ends), graph)
    l.filter_small(20)