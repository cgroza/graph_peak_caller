import numpy as np
import pybedtools
from pybedtools import BedTool
from offsetbasedgraph import IntervalCollection
from offsetbasedgraph.graphtraverser import GraphTraverserUsingSequence
import offsetbasedgraph as obg
from .linearsnarls import LinearSnarlMap
from .snarls import SnarlGraphBuilder, SnarlGraph
import pyvg
import logging

class LinearRegion(object):
    def __init__(self, chromosome, start, end):
        self.chromosome = chromosome
        self.start = start
        self.end = end

LRC_REGION = LinearRegion("chr19", 54025634, 55084318)
MHC_REGION = LinearRegion("chr6", 28510119, 33480577)


def bed_intervals_to_graph(obg_graph, linear_path_interval,
                           bed_file_name, graph_start_offset):
    peaks = BedTool(bed_file_name)
    intervals_on_graph = []
    for peak in peaks:
        start = peak.start - graph_start_offset
        end = peak.end - graph_start_offset
        intervals_on_graph.append(linear_path_interval.get_subinterval(start, end))

    return intervals_on_graph


def fasta_sequence_to_linear_path_through_graph(
        linear_sequence_fasta_file, sequence_retriever, ob_graph, start_node):
    search_sequence = open(linear_sequence_fasta_file).read()
    print("Length of search sequence: %d" % len(search_sequence))
    traverser = GraphTraverserUsingSequence(
        ob_graph, search_sequence, sequence_retriever)
    traverser.search_from_node(start_node)
    linear_path_interval = traverser.get_interval_found()
    return linear_path_interval


def get_linear_paths_in_graph(ob_graph, vg_graph, write_to_file_name=None):
    assert ob_graph is not None
    intervals = {}
    for path in vg_graph.paths:
        obg_interval = path.to_obg(ob_graph=ob_graph)
        obg_interval.name = path.name
        print("Path name: %s" % path.name)
        intervals[obg_interval.name] = obg_interval

    if write_to_file_name is not None:
        logging.info("Writing linear path to %s" % write_to_file_name)
        collection = obg.IntervalCollection(intervals.values())
        collection.to_file(write_to_file_name, text_file=True)

    return intervals


def sparse_maximum(indices1, values1, indices2, values2, genome_size):

    if indices1[0] != 0:
        np.insert(indices1, 0, 0)
        np.insert(values1, 0, 0)

    if indices2[0] != 0:
        np.insert(indices2, 0, 0)
        np.insert(values2, 0, 0)

    indices1 = np.insert(indices1, len(indices1), genome_size)
    indices2 = np.insert(indices2, len(indices2), genome_size)

    a = indices1[:-1] * 2
    b = indices2[:-1] * 2 + 1
    all_idxs = np.concatenate([a, b])
    all_idxs.sort()
    vi_list = [values1, values2]
    values_list = []
    for i, vals in enumerate(vi_list):
        idxs = np.nonzero((all_idxs % 2) == i)[0]
        all_values = vals
        value_diffs = np.diff(all_values)
        values = np.zeros(all_idxs.shape)
        values[idxs[1:]] = value_diffs
        values[idxs[0]] = all_values[0]
        values_list.append(values.cumsum())
    values = np.maximum(values_list[0], values_list[1])
    idxs = all_idxs // 2
    empty_ends = np.nonzero(np.diff(idxs) == 0)[0]
    max_values = np.maximum(values[empty_ends], values[empty_ends+1])
    values[empty_ends+1] = max_values
    values[empty_ends] = max_values

    indices = idxs
    values = values

    indices, values = sanitize_indices_and_values(indices, values)
    return indices, values


def continuous_sparse_maximum(indices1, values1, indices2, values2):
    all_indices = np.concatenate([indices1, indices2])
    # all_values = np.concatenate([values1, values2])
    codes = np.concatenate([np.zeros_like(indices1), np.ones_like(indices2)])
    sorted_args = np.argsort(all_indices)

    sorted_indices = all_indices[sorted_args]
    sorted_codes = codes[sorted_args]
    values_list = []
    for code, values in enumerate(values1, values2):
        my_args = sorted_codes == code
        diffs = np.diff(values)
        my_values = np.zeros(sorted_indices.shape)
        my_values[my_args[1:]] = diffs
        my_values[my_args[0]] = values[0]
        values_list.append(my_values.cumsum())

    values = np.maximum(values_list[0], values_list[1])
    empty_ends = np.nonzero(np.diff(sorted_indices) == 0)[0]
    max_values = np.maximum(values[empty_ends], values[empty_ends+1])
    values[empty_ends+1] = max_values
    values[empty_ends] = max_values
    indices, values = sanitize_indices_and_values(sorted_indices, values)
    return indices, values


def sanitize_indices_and_values(indices, values):

    new_indices = []
    new_values = []

    prev = None
    for i, index in enumerate(indices):
        if values[i] != prev:
            new_indices.append(index)
            new_values.append(values[i])
        prev = values[i]

    return new_indices, new_values


def create_linear_map(ob_graph, snarl_file_name = "haplo1kg50-mhc.snarls", out_file_name="linear_map", copy_graph=True):
    if copy_graph:
        ob_graph = ob_graph.copy()
    builder = SnarlGraphBuilder.from_vg_snarls(
        ob_graph,
        snarl_file_name)
    snarlgraph = builder.build_snarl_graphs()
    linear_map = LinearSnarlMap.from_snarl_graph(snarlgraph, ob_graph)
    linear_map.to_json_files(out_file_name)
    logging.info("Created linear snarl map, wrote to file %s" % out_file_name)

def create_ob_graph_from_vg(vg_json_graph_file_name, ob_graph_file_name="graph.obg"):
    vg_graph = pyvg.Graph.create_from_file(vg_json_graph_file_name)
    ob_graph = vg_graph.get_offset_based_graph()
    ob_graph.to_file(ob_graph_file_name)
    logging.info("Wrote obgraph to %s" % ob_graph_file_name)


def create_linear_path(ob_graph, vg_graph, path_name="ref", write_to_file="linear_path.intervalcollection"):
    assert ob_graph is not None
    linear_paths = get_linear_paths_in_graph(ob_graph, vg_graph, write_to_file_name=write_to_file)
    ref_path = linear_paths[path_name].to_indexed_interval()
    return ref_path

if __name__ == "__main__":
    """
    values = get_average_signal_values_within_peaks("../data/sample1_signal_1.bigwig", "../data/sample1_peaks_1.bed")
    values = values[np.logical_not(np.isnan(values))]
    values = values[values < 8]
    print("Mean", np.mean(values))
    print("Std:", np.std(values))
    plt.hist(values, 100)
    plt.show()
    #longest_segment("../data/sample1_signal_1.bedGraph")
    """
    from graph_peak_caller.peakcollection import PeakCollection, ReadCollection
    from pyvg.vg import Graph
    import logging
    logging.basicConfig(level=logging.INFO)

    ob_graph = obg.GraphWithReversals.from_file("../tests/mhc/graph.obg")
    vg_graph = Graph.create_from_file("../tests/mhc/graph.json")

    #print(vg_graph.paths.keys())

    linear_path = create_linear_path(ob_graph, vg_graph, path_name="ref")

    linear_reads = \
        ReadCollection.create_from_linear_intervals_in_bed_file(
                            ob_graph,
                            linear_path,
                            #"../tests/ENCFF639IFG_lrc.bed",
                            "ENCFF639IFG.bed",
                            graph_region=MHC_REGION)

    linear_reads.to_file("../tests/mhc/macs_reads_on_graph.intervals", text_file=True)
