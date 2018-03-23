import numpy as np
import logging
import offsetbasedgraph as obg
from pyvg.sequences import SequenceRetriever
from .analysis.peakscomparer import PeaksComparerV2, AnalysisResults
from .analysis.manually_classified_peaks import \
    CheckOverlapWithManuallyClassifiedPeaks
from .analysis.analyse_peaks import LinearRegion
from .analysis.differentialbinding import main
from .analysis.fimowrapper import FimoFile
from .peakcollection import PeakCollection
from .analysis.nongraphpeaks import NonGraphPeakCollection
from .analysis.motifenrichment import plot_true_positives
from .peakfasta import PeakFasta


def analyse_peaks_whole_genome(args):
    chromosomes = args.chromosomes.split(",")
    results = AnalysisResults()
    for chrom in chromosomes:
        graph = obg.GraphWithReversals.from_numpy_file(
            args.graphs_dir + chrom + ".nobg")
        logging.info("Reading linear path")
        linear_path = obg.NumpyIndexedInterval.from_file(
            args.graphs_dir + chrom + "_linear_pathv2.interval")

        analyser = PeaksComparerV2(
            graph,
            args.results_dir + "macs_sequences_chr%s_summits.fasta" % chrom,
            args.results_dir + "%s_sequences_summits.fasta" % chrom,
            args.results_dir + "/fimo_macs_chr%s/fimo.txt" % chrom,
            args.results_dir + "/fimo_graph_chr%s/fimo.txt" % chrom,
            linear_path
        )
        results = results + analyser.results

    print(" === Final results for all chromosomes ===")
    print(results)

    results.to_file(args.out_file + ".pickle")
    with open(args.out_file + ".txt", "w") as f:
        f.write(str(results))
    logging.info("Wrote results as pickle to %s and as text to %s"
                 % (args.out_file + ".pickle", args.out_file + ".txt"))


def analyse_manually_classified_peaks(args):
    for chromosome in args.chromosomes.split():
        graph_file_name = args.graphs_location + "/" + chromosome + ".nobg"
        graph = obg.GraphWithReversals.from_numpy_file(graph_file_name)
        CheckOverlapWithManuallyClassifiedPeaks.from_graph_peaks_in_fasta(
                graph,
                args.graphs_location + "/" + chromosome + ".json",
                chromosome,
                args.reads_base_name + chromosome + "_sequences.fasta",
                args.regions_file,
                args.manually_classified_peaks_file)


def analyse_peaks(args):
    graph = args.graph

    end = int(args.graph_end)
    if end == 0:
        region = None
    else:
        region = LinearRegion(args.graph_chromosome,
                              int(args.graph_start), end)
    linear_path = obg.NumpyIndexedInterval.from_file(
        args.linear_path_name)
    PeaksComparerV2(
        graph,
        args.linear_peaks_fasta_file_name,
        args.graph_peaks_fasta_file_name,
        args.linear_peaks_fimo_results_file,
        args.graph_peaks_fimo_results_file,
        linear_path,
        region=region)


def differential_expression(args):
    logging.info("Running differential expression.")
    test_name = args.test_name
    fimo_file_name = args.fimo_file_name
    peaks_file_name = "%s_max_paths.intervalcollection" % test_name
    subgraphs_file_name = "%s_sub_graphs.graphs.npz" % test_name
    node_ids_file_name = "%s_sub_graphs.nodeids.npz" % test_name
    graph = args.graph

    subgraphs = np.load(subgraphs_file_name)
    logging.info("Found %d subgraphs" % len(subgraphs.keys()))
    node_ids = np.load(node_ids_file_name)

    res = main(
        FimoFile.from_file(fimo_file_name),
        PeakCollection.from_file(peaks_file_name, True),
        subgraphs,
        node_ids,
        graph)
    retriever = obg.SequenceGraph.from_file(
        args.graph_file_name + ".sequences")
    out_file_name = test_name + "_diffexpr.fasta"
    out_f = open(out_file_name, "w")
    n = 0
    for expr_diff in res:
        n += 1
        main_seq = retriever.get_interval_sequence(expr_diff.main_path)
        out_f.write("> %s %s\n" % (expr_diff.peak_id, expr_diff.main_count))
        out_f.write(main_seq + "\n")
        var_seq = retriever.get_interval_sequence(expr_diff.var_path)
        out_f.write("> %sAlt %s\n" % (expr_diff.peak_id, expr_diff.var_count))
        out_f.write(var_seq + "\n")
    logging.info("Wrote %d lines to %s" % (n, out_file_name))
    out_f.close()


def plot_motif_enrichment(args):
    fasta1 = args.fasta1
    fasta2 = args.fasta2
    meme = args.meme_motif_file

    plot_true_positives(
        [
            ("Graph Peak Caller", fasta1),
            ("MACS2", fasta2)
        ],
        meme,
        plot_title=args.plot_title.replace("ARABIDOPSIS_", ""),
        save_to_file=args.out_figure_file_name,
        run_fimo=args.run_fimo == "True"
    )


def peaks_to_fasta(args):
    logging.info("Getting sequence retriever")
    retriever = obg.SequenceGraph.from_file(args.sequence_graph)
    logging.info("Getting intervals")
    intervals = PeakCollection.create_generator_from_file(
        args.intervals_file_name)
    logging.info("Writing to fasta")
    PeakFasta(retriever).save_intervals(args.out_file_name,
                                        intervals)


def linear_peaks_to_fasta(args):
    collection = NonGraphPeakCollection.from_bed_file(
        args.linear_reads_file_name)
    collection.set_peak_sequences_using_fasta(
        fasta_file_location=args.fasta_file)
    collection.save_to_sorted_fasta(args.out_file_name)
    logging.info("Saved sequences to %s" % args.out_file_name)

    window = 60
    if hasattr(args, "window"):
        if args.window is not None:
            window = int(args.window)
            logging.info("Using window size of %d" % window)

    summits = NonGraphPeakCollection.from_bed_file(
        args.linear_reads_file_name, cut_around_summit=window)
    summits.set_peak_sequences_using_fasta(
        fasta_file_location=args.fasta_file)
    out_name = args.out_file_name.split(".")[0] + "_summits.fasta"
    summits.save_to_sorted_fasta(out_name)
    logging.info("Saved summits to %s" % out_name)