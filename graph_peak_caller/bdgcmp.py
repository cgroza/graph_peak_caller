import shutil
from .pileup import Pileup
import subprocess

def create_background_pileup_as_max_from_pileups(graph, pileups):
    pileup_files = [p.to_bed_graph("pileup_%d.tmp" % i) for i, p in enumerate(pileups)]

    max_pileup = "pileup_max.tmp"
    shutil.copyfile("pileup_0.tmp", max_pileup)

    for pileup in pileup_files:
        max_of_two_pileups(max_pileup, pileup, max_pileup)

    return Pileup.from_bed_graph(graph, max_pileup)


def max_of_two_pileups(pileup1_filename, pileup2_filename, out_filename):
    command = ["macs2", "bdgcmp", "-m", "max", "-t", pileup1_filename, "-c", pileup2_filename, "-o", out_filename]
    output = subprocess.check_output(command)
    print(output)