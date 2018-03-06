import sys
from graph_peak_caller.peakscomparer import AnalysisResults
import logging

class HtmlReportGenerator:
    def __init__(self, transcription_factors):
        self.tfs = transcription_factors
        self.html = ""
        self._create_report_table()
        self._create_report_figures()

    def _write_table_row(self, tf, analysis_result):
        self.html += """
        <tr>
            <td>%s</td>
            <td>%d</td>
            <td>%d (%d)</td>
            <td>%d (%d)</td>
            <td>%d</td>
            <td>%d (%d)</td>
            <td>%d (%d)</td>
            <td>%d</td>
            <td>%d</td>
            <td>%d</td>
            <td>%d</td>
        </tr>
        """ % (tf,
               analysis_result.tot_peaks1,
               analysis_result.peaks1_in_peaks2,
               analysis_result.peaks1_in_peaks2_matching_motif,
               analysis_result.peaks1_not_in_peaks2,
               analysis_result.peaks1_not_in_peaks2_matching_motif,
               analysis_result.tot_peaks2,
               analysis_result.peaks2_in_peaks1,
               analysis_result.peaks2_in_peaks1_matching_motif,
               analysis_result.peaks2_not_in_peaks1,
               analysis_result.peaks2_not_in_peaks1_matching_motif,
               analysis_result.motif_ambiguous,
               analysis_result.motif_not_ambiguous,
               analysis_result.not_motif_ambiguous,
               analysis_result.not_motif_not_ambiguous
               )

    def _create_report_table(self):
        self.html += """
        <table class='table' style='margin-top: 40px;'>
            <h3>Overview of peaks found</h3>
            <thead>
                <tr>
                    <th></th>
                    <th colspan='3'>Graph Peak Caller</th>
                    <th colspan='3'>Macs2</th>
                    <th colspan='4'>Graph Peak Caller motif enrichment</th>
                </tr>
            </theads>
            <tr>
                <th>TF</th>
                <th># Peaks found</th>
                <th># Peaks also found by Macs2</th>
                <th># Peaks NOT found by Macs2</th>
                <th># Peaks found</th>
                <th># Peaks also found by Graph Peak Caller</th>
                <th># Peaks NOT found by Graph Peak Caller</th>
                <th># Ambiguous peaks hitting motif</th>
                <th># Not ambiguous peaks hitting motif</th>
                <th># Ambiguous peaks not hitting motif</th>
                <th># Not ambiguous peaks not hitting motif</th>
            </tr>
        """

        for tf in self.tfs:
            results = AnalysisResults.from_file("figures_tables/" + tf + ".pickle")
            self._write_table_row(tf, results)

        self.html += "</table>"

    def _create_report_figures(self):
        self.html += "<h3>Motifenrichment plots</h3>"
        for tf in self.tfs:
            self.html += "<img style='width: 300px; height: auto; padding: 50px;' src='" + tf + ".png'/>"

    def _html_start(self):
        return """
        <!doctype html>
        <html>
        <head>
            <link rel="stylesheet" href="bootstrap.min.css">
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">

            <title>Graph Peak Caller - Jenkins results</title>
        </head>
        <body>
        <div class="container" style='margin-top: 50px;'>

        <h1>Graph Peak Caller - experiment results</h1>
        """

    def _html_end(self):
        return "</div></body></html>"

    def write_report(self, file_name):
        f = open(file_name, "w")
        final_html = self._html_start() + self.html + self._html_end()
        f.write(final_html)
        f.close()


if __name__ == "__main__":
    transcription_factors = sys.argv[1].split(",")
    report_file_name = sys.argv[2]

    generator = HtmlReportGenerator(transcription_factors)
    generator.write_report(report_file_name)