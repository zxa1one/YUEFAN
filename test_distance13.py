import unittest
import server
class DistanceTests(unittest.TestCase):
    def test_independent_of_mode(self):
        r={'location':[114.3,35.71]}
        a=server.geographic_distance({'location':[114.3,35.7],'mode':'walk'},r)
        b=server.geographic_distance({'location':[114.3,35.7],'mode':'drive'},r)
        self.assertEqual(a,b)
        self.assertAlmostEqual(a['km'],1.11,places=2)
        self.assertNotIn('minutes',a)
    def test_unknown(self):
        self.assertIsNone(server.geographic_distance({'location':None},{'location':[114.3,35.71]})['km'])
