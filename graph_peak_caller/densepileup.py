import logging
from itertools import chain
import numpy as np
from scipy.stats import poisson
from collections import defaultdict
from .pileup import Pileup
from .pileupcleaner2 import PeaksCleaner, HolesCleaner
from .subgraphcollection import SubgraphCollection
from .eventsorter import DiscreteEventSorter
from offsetbasedgraph import Interval, IntervalCollection
import pickle
from .sparsepileup import SparseAreasDict, starts_and_ends_to_sparse_pileup, intervals_to_start_and_ends
from memory_profiler import profile
from .sparsepileupv2 import RpScore, SimpleValuedIndexes

class DensePileupData:

    def __init__(self, graph, ndim=1, base_value=0):
        self._values = None
        self._node_indexes = None
        self._graph = graph
        self.min_node = None
        self._touched_nodes = set()
        self.ndim = ndim

        self._create_empty(ndim, base_value=0)

    def _create_empty(self, ndim=1, base_value=0):
        self._nodes = sorted(self._graph.blocks.keys())
        sorted_nodes = self._nodes
        self.min_node = sorted_nodes[0]
        max_node = sorted_nodes[-1]
        span = max_node - self.min_node + 1
        n_elements = sum([self.node_size(block) for block in self._graph.blocks])

        if ndim > 1:
            self._values = np.zeros((n_elements, ndim), dtype=np.float16)
        else:
            self._values = np.zeros(n_elements)

        if base_value > 0:
            self._values += base_value

        self._node_indexes = np.zeros(span, dtype=np.uint32)
        offset = 0
        for i, node in enumerate(self._nodes):
            index = node - self.min_node
            self._node_indexes[index] = offset
            offset += self.node_size(node)

        logging.info("Dense pileup inited")

    def sum(self):
        return np.sum(self._values)

    def sanitize_node(self):
        return

    def node_size(self, node):
        return self._graph.node_size(node)

    def values(self, node):
        index = node - self.min_node
        start = self._node_indexes[index]
        end = start + self.node_size(node)
        return self._values[start:end]

    def values_in_range(self, node, start, end):
        index = node - self.min_node
        array_start = self._node_indexes[index] + start
        array_end = self._node_indexes[index] + end
        return self._values[array_start:array_end]

    def set_values(self, node, start, end, value):
        index = node - self.min_node
        array_start = self._node_indexes[index] + start
        array_end = self._node_indexes[index] + end
        self._values[array_start:array_end] = value
        self._touched_nodes.add(node)

    def add_value(self, node, start, end, value):
        index = node - self.min_node
        array_start = self._node_indexes[index] + start
        array_end = self._node_indexes[index] + end
        self._values[array_start:array_end] += value
        self._touched_nodes.add(node)

    def get_subset_max_value(self, node_id, start, end):
        return np.max(self.values(node_id)[start:end])

    def get_subset_sum(self, node_id, start, end):
        return np.sum(self.values(node_id)[start:end])

    def score(self, node_id, start, end):
        return RpScore(self.get_subset_max_value(node_id, start, end), \
               self.get_subset_sum(node_id, start, end))

    def scale(self, factor):
        self._values *= factor

    def fill_existing_hole(self, node, start, end, value):
        assert np.all(self.values_in_range(node, start, end) == 0)
        self.set_values(node, start, end, value)

    def get_sparse_indexes_and_values(self, node):

        if self.ndim == 1:
            values = self.values(node)
            diffs = np.ediff1d(values, to_begin=np.array([1]))
            indexes = np.where(diffs != 0)
            values = values[indexes]
            indexes = np.append(indexes, self.node_size(node))
            return indexes, values
        else:
            values = self.values(node)
            diffs1 = np.ediff1d(values[:,0], to_begin=np.array([1]))
            indexes1 = np.where(diffs1 != 0)
            values1 = values[indexes1][:,0]
            indexes1 = np.append(indexes1, self.node_size(node))

            diffs2 = np.ediff1d(values[:,1], to_begin=np.array([1]))
            indexes2 = np.where(diffs2 != 0)
            values2 = values[indexes2][:,1]
            indexes2 = np.append(indexes2, self.node_size(node))

            #print("Values: %s" % values1)
            #print("Values2: %s" % values2)

            indexes, values = self.combine_valued_indexes(indexes1, values1, indexes2, values2)
            indexes = np.append(indexes, self.node_size(node))
            return indexes, values
            #return indexes1, indexes2, values1, values2

    @classmethod
    def combine_valued_indexes(cls, indexes1, values1, indexes2, values2):
        a = indexes1[:-1]*2
        b = indexes2[:-1]*2+1
        all_idxs = np.concatenate([a, b])
        all_idxs.sort()

        values_list = []
        for i, vi in enumerate((values1, values2)):
            idxs = np.nonzero((all_idxs % 2) == i)[0]
            all_values = vi
            value_diffs = np.diff(all_values)
            values = np.zeros(all_idxs.shape)
            values[idxs[1:]] = value_diffs
            values[0] = all_values[0]
            values_list.append(values.cumsum())

        values = np.array([values_list[0], values_list[1]])
        idxs = all_idxs // 2
        unique_idxs = np.append(np.nonzero(np.diff(idxs))[0], len(idxs)-1)
        idxs = idxs[unique_idxs]
        values = values[:, unique_idxs]
        return (idxs, np.transpose(values))

    def find_valued_areas(self, node, value):
        # Return list of tuples (start, end) having this value inside
        all_indexes, values = self.get_sparse_indexes_and_values(node)
        idxs = np.where(values == value)[0]
        starts = all_indexes[idxs]
        ends = all_indexes[idxs+1]
        areas = list(chain(*zip(starts, ends)))
        return areas

    def nodes(self):
        return self._touched_nodes

    def copy(self):
        new = DensePileupData(self._graph)
        new._values = self._values
        return new

    def threshold_copy(self, cutoff):
        new = self.copy()
        new._values = new._values >= cutoff
        logging.info("Thresholding done.")
        return new

    def threshold(self, cutoff):
        self._values = self._values >= cutoff

    def index_value_pairs(self, node):
        indexes, values = self.get_sparse_indexes_and_values(node)
        assert len(indexes) >= 2
        assert len(values) >= 1
        lines = list(zip(
            indexes[:-1],
            indexes[1:],
            values
            ))
        assert len(lines) >= 1
        return lines

    def get_bed_graph_lines(self):
        for node in self.nodes():
            lines = self.index_value_pairs(node)
            for line in lines:
                yield "%s\t%s\t%s\t%s\n" % (node, line[0], line[1], line[2])

    def __len__(self):
        return len(self.nodes())

class DensePileup(Pileup):
    def __init__(self, graph, ndim=1, base_value=0):
        logging.info("Initing sparsepileup")
        self.graph = graph
        self.data = DensePileupData(graph, ndim=ndim, base_value=base_value)

    @classmethod
    def from_base_value(cls, graph, base_value):
        pileup = cls(graph, base_value=base_value)
        return pileup

    def __str__(self):
        out = "Densepileup \n"
        for node in self.data.nodes():
            out += "  Node %d: %s, %s\n" % (node, self.data.values(node), self.data.get_sparse_indexes_and_values(node))

        return out

    def __repr__(self):
        return self.__str__

    def sum(self):
        return self.data.sum()

    def mean(self):
        graph_size = sum([self.graph.node_size(b) for b in self.graph.blocks])
        mean = self.sum() / graph_size
        return mean

    def scale(self, scale):
        self.data.scale()

    def fill_small_wholes(self, max_size, write_holes_to_file=None, touched_nodes=None):
        cleaner = HolesCleaner(self, max_size, touched_nodes=touched_nodes)
        areas = cleaner.run()
        n_filled = 0

        hole_intervals = []

        for node_id in areas.areas:
            if touched_nodes is not None:
                if node_id not in touched_nodes:
                    continue

            starts = areas.get_starts(node_id)
            ends = areas.get_ends(node_id)
            for start, end in zip(starts, ends):
                logging.debug("Filling hole %s, %d, %d. Node size: %d" % (
                    node_id, start, end, self.graph.node_size(node_id)))

                if start == end:
                    logging.warning("Trying to fill hole of 0 length")
                    continue

                self.data.fill_existing_hole(node_id, start, end, True)

                n_filled += 1
                assert end - start <= max_size
                hole_intervals.append(Interval(start, end, [node_id]))

        logging.info(
            "Filled %d small holes (splitted into holes per node)" % n_filled)

        if write_holes_to_file is not None:
            intervals = IntervalCollection(hole_intervals)
            intervals.to_file(write_holes_to_file, text_file=True)

        self.sanitize()

    def sanitize(self):
        logging.info("Sanitizing sparse pileup")
        logging.info("Sanitize done")

    def find_valued_areas(self, value):
        return SparseAreasDict({node_id: self.data.find_valued_areas(node_id, value)
                               for node_id in self.data.nodes()
                                }, graph=self.graph)

    @classmethod
    def from_intervals(cls, graph, intervals):
        starts, ends = intervals_to_start_and_ends(graph, intervals)
        return cls.from_starts_and_ends(graph, starts, ends)

    @classmethod
    def from_starts_and_ends(cls, graph, starts, ends, dtype=bool):
        pileup = cls(graph)
        for node in starts:
            for i, start in enumerate(starts[node]):
                end = ends[node][i]
                pileup.data.add_value(node, start, end, 1)


        return pileup

    def to_subgraphs(self):
        raise NotImplementedError()
        # Returns a list of areas which each is a subgraph
        collection = SubgraphCollection.from_pileup(self.graph, self)
        return collection

    @classmethod
    def from_valued_areas(cls, graph, valued_areas, touched_nodes = None):
        pileup = cls(graph)

        if touched_nodes is None:
            nodes = graph.blocks
        else:
            nodes = touched_nodes

        i = 0
        # Fill pileup_data
        logging.info("N nodes to process: %d" % len(nodes))
        for rp in nodes:
            if i % 100000 == 0:
                logging.info("Creating sparse from valued areas for node %d" % i)
            i += 1

            length = graph.blocks[rp].length()
            starts = valued_areas.get_starts_array(rp, node_size=length)
            if len(starts) == 0:
                continue

            ends = valued_areas.get_ends_array(rp, node_size=length)
            if len(starts) == 0 and len(ends) == 0:
                continue

            assert len(starts) == len(ends)
            for start, end in zip(starts, ends):
                pileup.data.add_value(rp, start, end, 1)

        return pileup


    def threshold_copy(self, cutoff):
        new_pileup = self.__class__(self.graph)
        new_pileup.data = self.data.threshold_copy(cutoff)
        return new_pileup

    def threshold(self, cutoff):
        self.data.threshold(cutoff)

    @classmethod
    def from_bed_graph(cls, graph, filename):
        raise NotImplementedError()

    @classmethod
    def from_bed_file(cls, graph, filename):
        raise NotImplementedError()

    def to_bed_file(self, filename):
        raise NotImplementedError()

    def remove_small_peaks(self, min_size):
        logging.info("Initing cleaner")
        cleaner = PeaksCleaner(self, min_size)
        logging.info("Running cleaner")
        areas = cleaner.run()
        logging.info("Removing emty areas")

        logging.info("Creating pileup using results from cleaner")
        pileup = self.from_areas_collection(self.graph, [areas])
        logging.info("Tresholding")
        pileup.threshold(0.5)
        return pileup

    def to_bed_graph(self, filename):
        f = open(filename, "w")
        i = 0
        for line in self.data.get_bed_graph_lines():
            f.write(line)
            i += 1
        f.close()
        self.filename = filename
        self.is_written = True
        return filename

    @classmethod
    def from_pickle(cls, file_name, graph):
        with open("%s" % file_name, "rb") as f:
            data = pickle.loads(f.read())
            #assert isinstance(SparsePileupData, cls)
            obj = cls(graph)
            obj.data = data
            return obj

    def to_pickle(self, file_name):
        with open("%s" % file_name, "wb") as f:
            pickle.dump(self.data, f)

    def to_bed_file(self, filename):
        f = open(filename, "w")
        areas = self.find_valued_areas(True)
        for node_id, idxs in areas.items():
            for i in range(len(idxs)//2):
                interval = (node_id, idxs[2*i], idxs[2*i+1])
                f.write("%s\t%s\t%s\t.\t.\t.\n" % interval)
        f.close()
        return filename

class DenseControlSample(DensePileup):
    def get_p_dict(self):
        p_value_dict = defaultdict(dict)
        count_dict = defaultdict(int)
        baseEtoTen = np.log(10)
        for node in self.data.nodes():
            for start, end, val in self.data.index_value_pairs(node):
                if val[1] not in p_value_dict[val[0]]:
                    log_p_val = poisson.logsf(val[1], val[0])
                    p_value_dict[val[0]][val[1]] = -log_p_val/baseEtoTen
                p = p_value_dict[val[0]][val[1]]
                count_dict[p] += end-start

        p_value_dict[0.0][0.0] = -1
        count_dict[-1] = 0

        self.p_value_dict = p_value_dict
        self.count_dict = count_dict

    def get_p_to_q_values(self):
        p_value_counts = self.count_dict
        p_to_q_values = {}
        sorted_p_values = sorted(p_value_counts.keys(), reverse=True)
        rank = 1
        # logN = np.log10(self.graph.get_size())
        logN = np.log10(sum(p_value_counts.values()))
        pre_q = None
        for p_value in sorted_p_values:
            value_count = p_value_counts[p_value]
            q_value = p_value + (np.log10(rank) - logN)
            if np.isclose(p_value, 2.1326711212014025):
                print(q_value, logN, rank, np.log10(rank))
            if rank == 1:
                q_value = max(0.0, q_value)
            else:
                q_value = max(0.0, min(pre_q, q_value))
            p_to_q_values[p_value] = q_value
            pre_q = q_value
            rank += value_count
        self.p_to_q_values = p_to_q_values

    def get_q_values(self):
        def translation(x):
            return self.p_to_q_values[
                self.p_value_dict[x[0]][x[1]]]

        new_values = np.apply_along_axis(translation, 1, self.data._values)
        self.data._values = new_values
        self.data.ndim = 1

    def get_scores(self):
        logging.info("Creating p dict")
        self.get_p_dict()
        logging.info("Creating mapping from p-values to q-values")
        self.get_p_to_q_values()
        logging.info("Computing q values")
        self.get_q_values()

    @classmethod
    def from_sparse_control_and_sample(cls, control, sample):
        logging.info("Creating pileup by combining control and sample")
        pileup = cls(sample.graph, ndim=2)
        pileup.data._values[:,0] = control.data._values
        pileup.data._values[:,1] = sample.data._values

        assert np.all(control.data._nodes == sample.data._nodes)

        pileup.data._touched_nodes = sample.data._touched_nodes.union(control.data._touched_nodes)
        return pileup
