import pickle
from .sparsepileup import ValuedIndexes
from .linearintervals import LinearIntervalCollection


class LinearSnarlMap(object):
    def __init__(self, snarl_graph, graph):
        self._graph = graph
        self._length = snarl_graph.length()
        self._linear_node_starts, self._linear_node_ends = snarl_graph.get_distance_dicts()

    def get_node_start(self, node_id):
        return self._linear_node_starts[node_id]

    def __str__(self):
        out = "Linear snarl map \n"
        out += " Starts: \n"
        for node, val in self._linear_node_starts.items():
            out += "  %d, %.3f \n" % (node, val)
        out += " Ends: \n"
        for node, val in self._linear_node_ends.items():
            out += "  %d, %.3f \n" % (node, val)

        return out

    def __repr__(self):
        return self.__str__()

    def get_node_end(self, node_id):
        return self._linear_node_ends[node_id]

    def get_scale_and_offset(self, node_id):
        linear_length = self.get_node_end(node_id) \
                        - self.get_node_start(node_id)
        node_length = self._graph.node_size(node_id)
        scale = linear_length/node_length
        offset = self.get_node_start(node_id)
        return scale, offset

    def to_graph_pileup(self, unmapped_indices_dict):
        vi_dict = {}
        for node_id, unmapped_indices in unmapped_indices_dict.items():
            scale, offset = self.get_scale_and_offset(node_id)
            new_idxs = (unmapped_indices.get_index_array()-offset) / scale
            new_idxs = new_idxs.astype("int")
            new_idxs[0] = max(0, new_idxs[0])
            vi = ValuedIndexes(
                new_idxs[1:], unmapped_indices.get_values_array()[1:],
                unmapped_indices.values[0],
                self._graph.node_size(node_id))
            if vi.indexes.size:
                if not vi.indexes[-1] <= vi.length:
                    print(node_id, scale, offset)
                    print(unmapped_indices)
                    print(new_idxs)
                    raise
            vi.sanitize_indices()
            vi.sanitize()
            vi_dict[node_id] = vi
        return vi_dict

    def map_graph_interval(self, interval):
        start_pos = self.graph_position_to_linear(interval.start_position)
        end_pos = self.graph_position_to_linear(interval.end_position)
        return start_pos, end_pos

    def graph_position_to_linear(self, position):
        node_id = abs(position.region_path_id)
        node_start = self._linear_node_starts[node_id]
        node_end = self._linear_node_ends[node_id]
        node_size = self._graph.node_size(position.region_path_id)
        scale = (node_end-node_start) / node_size
        if position.region_path_id > 0:
            return node_start + scale*position.offset
        else:
            return node_end - scale*position.offset

    @classmethod
    def from_snarl_graph(cls, snarl_graph):
        return cls(snarl_graph)

    def map_interval_collection(self, interval_collection):
        starts = []
        ends = []
        for interval in interval_collection:
            start, end = self.map_graph_interval(interval)
            starts.append(start)
            ends.append(end)
        return LinearIntervalCollection(starts, ends)

    def to_file(self, file_name):
        with open("%s" % file_name, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def from_file(cls, file_name):
        with open("%s" % file_name, "rb") as f:
            obj = pickle.loads(f.read())
            assert isinstance(obj, cls)
            return obj

