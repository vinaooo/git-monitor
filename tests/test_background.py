import unittest

from painel.background import options


class BackgroundTest(unittest.TestCase):
    def test_options(self):
        o = options(True, ('painel', '--x'))
        self.assertEqual((o['autostart'].unpack(), o['commandline'].unpack()), (True, ['painel', '--x']))
        self.assertFalse(options(False)['autostart'].unpack())
