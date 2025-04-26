import unittest
from Orange.widgets.tests.base import WidgetTest

from orangecontrib.example.widgets.mywidget import Scatter3DWidget


class Vis3dTests(unittest.TestCase):
    def test_addition(self):
        self.assertEqual(1 + 1, 2)


class TestScatter3DWidget(WidgetTest):
    def setUp(self):
        self.widget = self.create_widget(Scatter3DWidget)

    def test_addition(self):
        self.assertEqual(1 + 1, 2)
