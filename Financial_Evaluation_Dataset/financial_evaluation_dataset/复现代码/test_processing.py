import unittest
from build_candidates import choice_letters, numeric_labels, causal_labels


class ProcessingTests(unittest.TestCase):
    def test_multiselect_json_and_chinese_delimiters(self):
        options = {'A': '股票', 'B': '债券', 'C': '基金'}
        self.assertEqual(choice_letters('["C","A"]', options), 'AC')
        self.assertEqual(choice_letters('A、C', options), 'AC')

    def test_true_false_uses_option_text_not_assumed_order(self):
        self.assertEqual(choice_letters('错误', {'A': '错误', 'B': '正确'}), 'A')
        self.assertEqual(choice_letters('错误', {'A': '正确', 'B': '错误'}), 'B')

    def test_missing_option_is_rejected(self):
        self.assertIsNone(choice_letters('["A","E"]', {'A': '甲', 'B': '乙'}))
        self.assertIsNone(choice_letters('[1, 2]', {'A': '甲', 'B': '乙'}))

    def test_negative_units_and_evidence_offsets(self):
        text = '本期净利润为-1,200.50万元。营业收入为2亿元。'
        values = numeric_labels(text)
        self.assertEqual([x['normalized_value'] for x in values], ['-12005000.00', '200000000'])
        for value in values:
            self.assertEqual(text[value['start']:value['end']], value['text'])
        self.assertEqual(numeric_labels('营业收入12.5，单位未提供。'), [])

    def test_reverse_causal_cue_and_offsets(self):
        text = '营业利润大幅下降主要系原材料价格持续上涨。'
        label = causal_labels(text)[0]
        self.assertIn('原材料', label['cause']['text'])
        self.assertIn('营业利润', label['effect']['text'])
        for key in ['cause', 'effect']:
            span = label[key]
            self.assertEqual(text[span['start']:span['end']], span['text'])

    def test_additional_cause_is_not_mistaken_for_effect(self):
        text = '公司产品销量同比下滑22.80%，主要由于一季度疫情影响，叠加生产工艺要求较高的高端产品销量占比提升所致。'
        label = causal_labels(text)[0]
        self.assertIn('销量同比下滑', label['effect']['text'])
        self.assertIn('疫情影响', label['cause']['text'])
        self.assertIn('叠加', label['cause']['text'])
        forward = causal_labels('由于原材料价格持续上涨，因此公司营业利润大幅下降。')[0]
        self.assertIn('原材料', forward['cause']['text'])
        self.assertIn('营业利润', forward['effect']['text'])

    def test_earnings_per_share_keeps_denominator(self):
        value = numeric_labels('基本每股收益0.50元。')[0]
        self.assertEqual(value['normalized_unit'], '元/股')


if __name__ == '__main__':
    unittest.main()
