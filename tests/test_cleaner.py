import unittest
from graph_peak_caller.sparsepileup import SparsePileup
from graph_peak_caller.extender import Areas
# from graph_peak_caller.pileupcleaner import PileupCleaner,  IntervalWithinBlock
from graph_peak_caller.pileupcleaner2 import PeaksCleaner, HolesCleaner
from cyclic_graph import get_small_cyclic_graph, get_large_cyclic_graph,\
    get_padded_cyclic_graph
import offsetbasedgraph as obg
from random import randrange, seed

class CleanupTester(unittest.TestCase):
    def assertIntervalsGiveSamePileup(self, areas, true_intervals):
        if not areas.areas:
            print(areas)
            self.assertEqual(len(true_intervals), 0)

        pileup = SparsePileup.from_areas_collection(
            areas.graph,
            [areas])
        pileup.threshold(1)
        true_pileup = SparsePileup.from_intervals(
            true_intervals[0].graph,
            true_intervals)
        true_pileup.threshold(1)

        print("Pileup from areas")
        print(pileup)
        print("Pileup from intervals")
        print(true_pileup)


        self.assertEqual(pileup, true_pileup)


class TestCyclicCleanup(CleanupTester):
    def setUp(self):
        self.small_graph = get_small_cyclic_graph()
        self.large_graph = get_large_cyclic_graph()
        self.padded_graph = get_padded_cyclic_graph()



    def test_loop_with_surrounding(self):
        start_intervals = [obg.Interval(
            90, 100, [1, 2],
            graph=self.padded_graph)]
        pileup = SparsePileup.from_intervals(
            self.padded_graph, start_intervals)
        pileup.threshold(1)
        cleaner = PeaksCleaner(pileup, 400)
        areas = cleaner.run()
        self.assertIntervalsGiveSamePileup(areas, start_intervals)

    def test_loop_with_surrounding_fail(self):
        start_intervals = [obg.Interval(
            90, 90, [1, 2],
            graph=self.padded_graph)]
        pileup = SparsePileup.from_intervals(
            self.padded_graph, start_intervals)
        pileup.threshold(1)
        cleaner = PeaksCleaner(pileup, 400)
        areas = cleaner.run()
        self.assertEqual(areas.areas, {})

    def test_loop_with_start_and_end_intervals(self):
        start_intervals = [
            obg.Interval(
                90, 10, [1, 2],
                graph=self.padded_graph),
            obg.Interval(
                90, 100, [2],
                graph=self.padded_graph)]
        pileup = SparsePileup.from_intervals(
            self.padded_graph, start_intervals)
        pileup.threshold(1)
        cleaner = PeaksCleaner(pileup, 400)
        areas = cleaner.run()
        self.assertEqual(areas.areas, {})


class CyclicHolesClean(TestCyclicCleanup):
    def setUp(self):
        super().setUp()
        nodes = {i: obg.Block(100) for i in range(1, 11)}
        edges = {i: [i+1] for i in range(1, 10)}
        self.lin_graph = obg.GraphWithReversals(nodes, edges)
        edges = {i: [i+1, (i+5) % 5 +1 ] for i in range(1, 5)}
        self.double_graph = obg.GraphWithReversals(nodes, edges)

    def test_lin(self):
        intervals = [
            obg.Interval(80, 20, [1, 2]),
            obg.Interval(41, 90, [2]),
            obg.Interval(10, 50, [3]),
            obg.Interval(70, 100, [3]),
            obg.Interval(20, 50, [4])]

        for i in intervals:
            i.graph = self.lin_graph
        pileup = SparsePileup.from_intervals(self.lin_graph, intervals)
        pileup.threshold(1)
        cleaner = HolesCleaner(pileup, 20)
        areas = cleaner.run()
        print("!!!!!!!!!!!!!!!!!!")
        print(areas)
        true_areas = Areas(self.lin_graph,
                           {2: [90, 100],
                            3: [0, 10, 50, 70],
                            4: [0, 20]})
        self.assertEqual(areas, true_areas)

    def test_simple(self):
        start_intervals = [
            obg.Interval(10, 40, [2], graph=self.padded_graph),
            obg.Interval(50, 90, [2], graph=self.padded_graph)]
        pileup = SparsePileup.from_intervals(
            self.padded_graph, start_intervals)
        pileup.threshold(1)
        cleaner = HolesCleaner(pileup, 40)
        areas = cleaner.run()
        self.assertEqual(areas, Areas(self.padded_graph, {2: [0, 10, 40, 50, 90, 100]}))
        pileup.fill_small_wholes(40)
        true_pileup = SparsePileup.from_intervals(
            self.padded_graph,
            [obg.Interval(0, 100, [2], graph=self.padded_graph)])
        true_pileup.threshold(1)
        self.assertEqual(pileup, true_pileup)

    def test_cycle(self):
        start_intervals = [
            obg.Interval(0, 100, [1], graph=self.padded_graph),
            obg.Interval(0, 100, [3], graph=self.padded_graph)]
        pileup = SparsePileup.from_intervals(
            self.padded_graph, start_intervals)
        pileup.threshold(1)
        cleaner = HolesCleaner(pileup, 40)
        areas = cleaner.run()
        true_areas = Areas(self.padded_graph, {})
        self.assertEqual(areas, true_areas)


class TestExhaustiveCleaner(unittest.TestCase):
    def setUp(self):
        nodes = {i: obg.Block(10) for i in range(1, 11)}
        edges = {i: [i+1, i+6] for i in range(1, 6)}
        self.graph = obg.GraphWithReversals(nodes, edges)


class TestCleanerOnRandomGraphs(CleanupTester):
    def setUp(self):
        from collections import defaultdict

        self.n_blocks = 40 #  5
        self.n_edges = self.n_blocks + 70 # +2
        blocks = {}
        blocks_list = []
        for i in range(1, self.n_blocks + 1):
            blocks[i] = obg.Block(3)
            blocks_list.append(i)

        # Random edges
        edge_dict = defaultdict(list)
        for i in range(0, self.n_edges):
            start = blocks_list[randrange(0, len(blocks_list))]
            end = blocks_list[randrange(0, len(blocks_list))]

            if randrange(0, 2) == 1:
                start = -start

            if randrange(0, 2) == 1:
                end = -end

            if end == start or end == -start:
                continue

            if end not in edge_dict[start]:
                edge_dict[start].append(end)

        self.graph = obg.Graph(blocks, edge_dict)
        print(self.graph)

    def setUpRandomIntervals(self, with_hole=False):
         # Create random interval
        start_rp = randrange(1, self.n_blocks + 1)
        start_offset = randrange(0, 3)
        end_offset = max(randrange(0, 3), start_offset + 1)
        rps = [start_rp]
        prev_rp = start_rp
        for i in range(0, self.n_blocks):
            edges = self.graph.adj_list[prev_rp]
            if len(edges) == 0:
                break
            rp = edges[randrange(0, len(edges))]
            prev_rp = rp
            if rp in rps:
                break

            rps.append(rp)

        self.intervals = [obg.Interval(start_offset, end_offset, rps, self.graph)]

        if with_hole:
            # Split interval at random position
            split_rp = randrange(0, len(rps))
            if split_rp > 0:
                split_pos = randrange(0, 2)
            else:
                split_pos = start_offset + 1

            split_end = split_pos
            first_interval_rps = rps[0:split_rp + 1]
            if split_pos == 0:
                first_interval_rps = first_interval_rps[0:split_rp]
                split_end = 2

            start_interval = obg.Interval(start_offset, split_end, first_interval_rps, self.graph)
            end_interval = obg.Interval(split_pos, end_offset, rps[split_rp:], self.graph)
            self.intervals = [start_interval, end_interval]
            hole_rps = [first_interval_rps[-1]]
            hole_end = split_pos
            if rps[split_rp] != hole_rps[0]:
                hole_rps.append(rps[split_rp])

            if hole_end == 0:
                hole_end = 3
                hole_rps = hole_rps[:-1]

            self.hole_interval = obg.Interval(split_end, hole_end, hole_rps, self.graph)
            if start_interval.contains(self.hole_interval) or end_interval.contains(self.hole_interval) \
                    or start_interval.contains(self.hole_interval.get_reverse()) \
                    or end_interval.contains(self.hole_interval.get_reverse()):
                self.hole_interval = obg.Interval(0, 0, [1], self.graph)  # Use empty hole

            self.intervals_without_holes = [obg.Interval(start_offset, end_offset, rps, self.graph)]

    def test_filter_intervals(self):
        seed(1)
        for i in range(0, 200):
            print(" ======== TEst case =======")
            self.setUp()
            self.setUpRandomIntervals()
            #print(self.graph)
            #print(self.intervals)
            pileup = SparsePileup.from_intervals(
            self.graph, self.intervals)
            pileup.threshold(1)
            cleaner = PeaksCleaner(pileup, 1)
            areas = cleaner.run()
            #print("Areas")
            #print(areas)
            self.assertIntervalsGiveSamePileup(areas, self.intervals)

    def test_fill_holes(self):
        seed(1)
        n_cases_checked = 0
        for i in range(0, 200):
            print(" ======== TEst case =======")
            self.setUp()
            self.setUpRandomIntervals(True)

            if self.hole_interval.length() == 0:
                continue

            if self.intervals[0].length() == 0 or self.intervals[1].length() == 0:
                continue

            n_cases_checked += 1

            #print(self.graph)
            #print(self.intervals)
            pileup = SparsePileup.from_intervals(
            self.graph, self.intervals)
            pileup.threshold(1)
            cleaner = HolesCleaner(pileup, 1)
            areas = cleaner.run()
            """
            print("--Intervals with hole")
            print(self.intervals)
            print("--Intervals without holes")
            print(self.intervals_without_holes)
            print("--Hole interval")
            print(self.hole_interval)
            print("--Areas")
            print(areas)
            """

            holes_found = areas.to_simple_intervals()
            correct_holes = [self.hole_interval]
            for hole in correct_holes:
                self.assertTrue(hole in holes_found or hole.get_reverse() in holes_found)

            for hole in holes_found:
                self.assertTrue(hole.length() <= 1)


            #pileup_correct = SparsePileup.from_intervals(self.graph, self.intervals_without_holes)
            #print(pileup_correct)
            #self.assertIntervalsGiveSamePileup(areas, [self.hole_interval])

        print("Checked %d cases" % n_cases_checked)


if __name__ == "__main__":
    unittest.main()