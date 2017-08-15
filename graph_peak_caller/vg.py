import json
import offsetbasedgraph
from collections import defaultdict
import pickle
import os


class Position(object):
    def __init__(self, node_id, offset, is_reverse=False):
        self.node_id = node_id
        self.offset = offset
        self.is_reverse = is_reverse

    def to_obg(self):
        return offsetbasedgraph.Position(self.node_id, self.offset)

    @classmethod
    def from_json(cls, position_dict):
        offset = int(position_dict["offset"]) if "offset" in position_dict else 0
        node_id = position_dict["node_id"]
        is_reverse = False
        if "is_reverse" in position_dict:
            is_reverse = position_dict["is_reverse"]
        return cls(node_id, offset, is_reverse)


class Edit(object):
    def __init__(self, to_length, from_length, sequence):
        self.to_length = to_length
        self.from_length = from_length
        self.sequence = sequence

    @classmethod
    def from_json(cls, edit_dict):
        sequence = None if "sequence" not in edit_dict else edit_dict["sequence"]
        to_length = edit_dict["to_length"] if "to_length" in edit_dict else 0
        from_length = edit_dict["from_length"] if "from_length" in edit_dict else 0
        return cls(to_length, from_length, sequence)


class Mapping(object):
    def __init__(self, start_position, edits):
        self.start_position = start_position
        self.edits = edits

    def is_reverse(self):
        return self.start_position.is_reverse

    def get_start_position(self):
        offset = self.start_position.offset
        if self.is_reverse():
            return Position(self.start_position.node_id, offset)
        else:
            return Position(self.start_position.node_id, offset)

    def get_end_position(self):
        offset = self.start_position.offset
        length = sum(edit.from_length for edit in self.edits)
        if self.is_reverse():
            return Position(self.start_position.node_id, offset+length)
        else:
            return Position(self.start_position.node_id, offset+length)

    @classmethod
    def from_json(cls, mapping_dict):
        start_position = Position.from_json(mapping_dict["position"])
        edits = [Edit.from_json(edit) for edit in mapping_dict["edit"]]
        return cls(start_position, edits)


class Path(object):
    def __init__(self, name, mappings):
        self.mappings = mappings
        self.name = name

    def is_reverse(self):
        mapping_reverse = [mapping.is_reverse() for mapping in self.mappings]
        assert all(is_reverse == mapping_reverse[0] for is_reverse in mapping_reverse), mapping_reverse
        return mapping_reverse[0]

    @classmethod
    def from_json(cls, path_dict):
        name = path_dict["name"] if "name" in path_dict else None

        mappings = []
        if "mapping" in path_dict:
            mappings = [Mapping.from_json(mapping) for mapping in path_dict["mapping"]]

        return cls(name, mappings)

    def to_obg(self):

        if len(self.mappings) == 0:
            return offsetbasedgraph.Interval(0, 0, [])

        nodes = [mapping.start_position.node_id for mapping in self.mappings]
        if self.is_reverse():
            nodes = nodes[::-1]
            start_pos = self.mappings[-1].get_start_position().to_obg()
            end_pos = self.mappings[0].get_end_position().to_obg()
        else:
            start_pos = self.mappings[0].get_start_position().to_obg()
            end_pos = self.mappings[-1].get_end_position().to_obg()
        return offsetbasedgraph.Interval(start_pos, end_pos, nodes)


class Node(object):
    def __init__(self, name, id, n_basepairs):
        self.name = name
        self.id = id
        self.n_basepairs = n_basepairs

    @classmethod
    def from_json(cls, json_object):
        name = ""
        if "name" in json_object:
            name = json_object["name"]

        return cls(name, json_object["id"], len(json_object["sequence"]))

    def to_obg(self):
        return offsetbasedgraph.Block(self.n_basepairs)


class Edge(object):
    def __init__(self, from_node, to_node, from_start, to_end, overlap):
        self.from_node = from_node
        self.to_node = to_node
        self.from_start = int(from_start)
        self.to_end = int(to_end)
        self.overlap = int(overlap)

    @classmethod
    def from_json(cls, json_object):

        from_start = False
        to_end = False
        overlap = 0

        if "from_start" in json_object:
            from_start = json_object["from_start"]
            # Parsed by json == "True"  # NB: Is True correct?

        if "to_end" in json_object:
            to_end = json_object["to_end"]  # == "True"

        if "overlap" in json_object:
            overlap = int(json_object["overlap"])

        return cls(json_object["from"],
                   json_object["to"],
                   from_start,
                   to_end,
                   overlap,
                   )


class Alignment(object):
    def __init__(self, path, identity):
        self.identity = identity
        self.path = path

    @classmethod
    def from_json(cls, alignment_dict):
        return cls(
            Path.from_json(alignment_dict["path"]),
            alignment_dict["identity"])


class Graph(object):

    def __init__(self, nodes, edges, paths):
        self.nodes = nodes
        self.edges = edges
        self.paths = paths

    @classmethod
    def create_from_file(cls, json_file_name, max_lines_to_read=False, limit_to_chromosome=False, do_read_paths=True):
        paths = []
        edges = []
        nodes = []
        f = open(json_file_name)
        lines = f.readlines()
        n_lines = len(lines)
        print("Number of lines: %d" % n_lines)

        # object_types = ["Path", "Edge", "Node"]
        i = 0
        for line in lines:
            line = json.loads(line)
            print("Line: %d/%d" % (i, n_lines))
            i += 1
            if limit_to_chromosome:
                if "path" not in line:
                    continue
                if line["path"][0]["name"] != limit_to_chromosome:
                    continue

            if do_read_paths and "path" in line:
                paths.extend([Path.from_json(json_object) for json_object in line["path"]])
            if "node" in line:
                nodes.extend([Node.from_json(json_object) for json_object in line["node"]])
            if "edge" in line:
                edges.extend([Edge.from_json(json_object) for json_object in line["edge"]])                

            if max_lines_to_read and i >= max_lines_to_read:
                break

        obj = cls(nodes, edges, paths)
        if do_read_paths:
            obj._merge_paths_by_name()
            obj.paths_as_intervals_by_chr = {}

        return obj

    def _interval_has_no_edges_in(self, interval):
        for edge in self.edges:
            if edge.to_node == interval.region_paths[0]:
                return False
        return True

    def edges_from_node(self, node_id):
        edges = []
        for edge in self.edges:
            if edge.from_node == node_id:
                edges.append(edge.to_node)

        return edges

    def _merge_paths_by_name(self):
        # Join all paths with the same name
        paths_by_name = defaultdict(list)
        for path in self.paths:
            paths_by_name[path.name].append(path)

        for name in paths_by_name:
            print(name)
            intervals = []
            for path in paths_by_name[name]:
                intervals.append(path.to_obg())

            #if name == "chr4":
            #    print(intervals)

            # Create a single connectected interval for this name
            region_paths = []
            # Find the starting interval (no edges in)
            start_intervals = []
            for interval in intervals:
                if self._interval_has_no_edges_in(interval):
                    start_intervals.append(interval)
            assert len(start_intervals) == 1

            # Traverse to connect all intervals
            current_interval = start_intervals[0]
            start_position = current_interval.start_position
            number_of_intervals_added = 0
            while True:
                region_paths.extend(current_interval.region_paths)
                number_of_intervals_added += 1
                next_nodes = self.edges_from_node(current_interval.region_paths[-1])
                potential_next_intervals = []
                for potential_next_interval in intervals:
                    if potential_next_interval.region_paths[0] in next_nodes:
                        potential_next_intervals.append(potential_next_interval)

                assert len(potential_next_intervals) <= 1

                if len(potential_next_intervals) == 0:
                    break

                current_interval = potential_next_intervals[0]

            end_position = current_interval.end_position

            single_linear_interval = offsetbasedgraph.Interval(start_position, end_position, region_paths)
            assert number_of_intervals_added == len(intervals)
            print(single_linear_interval)

            self.paths_as_intervals_by_chr[name] = single_linear_interval

    @classmethod
    def from_file(cls, file_name):
        """
        Load graph from pickle

        :param file_name: File name
        :rtype: Graph
        """
        if os.path.isfile("%s" % file_name):
            obj = pickle.load(open(file_name, "rb"))
            return cls(obj.nodes, obj.edges, obj.paths)
        else:
            print("Warning: Graph not found" % file_name)
            return None

    def to_file(self, file_name):
        """
        Writes the graph to file so that it later can be
        recreated using the from_file method

        :param file_name: File name
        :return:
        """
        with open("%s" % file_name, "wb") as f:
            pickle.dump(self, f)

    def get_offset_based_graph(self):
        offset_based_edges = defaultdict(list)
        for edge in self.edges:
            offset_based_edges[edge.from_node].append(edge.to_node)

        offset_based_blocks = {}
        for block in self.nodes:
            offset_based_blocks[block.id] = block.to_obg()
        print(offset_based_blocks)
        return offsetbasedgraph.Graph(offset_based_blocks,
                                      offset_based_edges)

    def get_translation(self, limit_to_chromosome=False):
        offset_based_graph = self.get_offset_based_graph()

        trans_dict = {}
        trans_dict_reverse = defaultdict(list)

        for chromosome in self.paths_as_intervals_by_chr:
            if limit_to_chromosome and limit_to_chromosome != chromosome:
                print("Skipping %s" % chromosome)
                continue

            offset_based_graph_path = self.paths_as_intervals_by_chr[chromosome]
            trans_dict[chromosome] =  [offset_based_graph_path]

            # Create reverse dict
            offset = 0


            for block in offset_based_graph_path.region_paths:
                block_length = offset_based_graph.blocks[block].length()



                trans_dict_reverse[block] = [
                            offsetbasedgraph.Interval(offset, offset + block_length, [chromosome], offset_based_graph)]
                offset += block_length

        return offsetbasedgraph.Translation(trans_dict, trans_dict_reverse, offset_based_graph)


if __name__ == "__main__":

    f = open("./dm_test_data/mapped_reads_sample.json")
    jsons = (json.loads(line) for line in f.readlines())
    alignments = [Alignment.from_json(json_dict) for json_dict in jsons]
    for alignment in alignments:
        print(alignment.path.is_reverse(), alignment.path.to_obg())