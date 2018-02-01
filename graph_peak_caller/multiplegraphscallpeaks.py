import offsetbasedgraph as obg
from pyvg.util import vg_json_file_to_interval_collection
from .experiment_info import ExperimentInfo
from .callpeaks import CallPeaks, Configuration
from .pvalues import PToQValuesMapper
from .densepileup import DensePileup
import logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s, %(levelname)s: %(message)s")


class MultipleGraphsCallpeaks:

    def __init__(self, graph_names, graph_file_names,
                 samples,
                 controls, linear_maps,
                 fragment_length, read_length,
                 has_control=False,
                 sequence_retrievers=None,
                 out_base_name="multigraphs_",
                 skip_filter_duplicates=False,
                 save_tmp_results_to_file=False
                 ):

        self._config = Configuration(
            skip_read_validation=True, save_tmp_results_to_file=save_tmp_results_to_file,
            skip_filter_duplicates=skip_filter_duplicates, p_val_cutoff=0.05,
            graph_is_partially_ordered=True)
        self.names = graph_names
        self.graph_file_names = graph_file_names
        self.fragment_length = fragment_length
        self.read_length = read_length
        self.linear_maps = linear_maps
        self.has_control = has_control
        self._base_name = out_base_name
        self.sequence_retrievers = sequence_retrievers
        self.samples = samples
        self.controls = controls
        self.run()

    @classmethod
    def from_file_base_names(cls):
        # Create lists of names, graphs, sample, control linear maps
        pass

    def run(self):
        self.run_to_p_values()
        self.create_joined_q_value_mapping()
        self.run_from_p_values()

    def run_to_p_values(self):
        for name, graph_file_name, sample, control, lin_map in \
            zip(self.names, self.graph_file_names,
                self.samples, self.controls, self.linear_maps):
            logging.info("Running %s" % name)
            ob_graph = obg.GraphWithReversals.from_unknown_file_format(
                graph_file_name)
            if isinstance(sample, obg.IntervalCollection):
                logging.info("Sample is already intervalcollection.")
            else:
                logging.info("Creating interval collecftions from files")
                sample = vg_json_file_to_interval_collection(
                    None, sample, ob_graph)
                control = vg_json_file_to_interval_collection(
                    None, control, ob_graph)

            graph_size = ob_graph.number_of_basepairs()
            info = ExperimentInfo(
                graph_size, self.fragment_length, self.read_length)
            CallPeaks.run_from_intervals(
                ob_graph, sample, control, info, self._base_name + name + "_",
                self.has_control,
                lin_map, self._config,
                stop_after_p_values=True
            )
            logging.info("Done until p values for %d")

    def create_joined_q_value_mapping(self):
        mapper = PToQValuesMapper.from_files(self._base_name)
        self._q_value_mapping = mapper.get_p_to_q_values()

    def run_from_p_values(self):
        for i, name in enumerate(self.names):
            graph_file_name = self.graph_file_names[i]
            ob_graph = obg.GraphWithReversals.from_unknown_file_format(
                graph_file_name)
            graph_size = sum(
                block.length() for block in ob_graph.blocks.values())
            info = ExperimentInfo(
                graph_size, self.fragment_length, self.read_length)
            assert ob_graph is not None
            caller = CallPeaks(ob_graph, self._base_name + name + "_")
            caller.p_to_q_values_mapping = self._q_value_mapping
            caller.p_values_pileup = DensePileup.from_sparse_files(
                ob_graph, self._base_name + name + "_" + "pvalues")
            caller.get_q_values()
            caller.call_peaks_from_q_values(
                experiment_info=info, config=self._config)
            if self.sequence_retrievers is not None:
                caller.save_max_path_sequences_to_fasta_file(
                    "sequences.fasta", self.sequence_retrievers.__next__())