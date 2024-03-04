# Dummy file for toolchain setup

import unittest


class TestSimple(unittest.TestCase):
    def test_pass(self):
        # self.assertTrue(True)
        assert True

    # def test_fail(self):
    #     # self.assertTrue(False)
    #     # assert False
    #     raise AssertionError


if __name__ == "__main__":
    unittest.main()
