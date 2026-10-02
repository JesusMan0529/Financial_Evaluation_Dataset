import unittest
from prepare_text import numeric_annotations, clear_causal, clear_opinion
from prepare_knowledge import rejection_reasons, key_for


class ProcessingChecks(unittest.TestCase):
    def test_question_decimal_not_removed_by_dedup(self):
        opts = {'A': '100', 'B': '200'}
        a = {'text':'贷款利率为3.5%\nA. 100\nB. 200', 'annotations':{'options':opts}}
        b = {'text':'贷款利率为35%\nA. 100\nB. 200', 'annotations':{'options':opts}}
        self.assertNotEqual(key_for(a), key_for(b))

    def fields(self, body):
        title = '测试公司:2022年年度报告'
        return numeric_annotations('报告：' + title + '\n正文：' + body, title, body)

    def test_current_and_prior_year(self):
        a = self.fields('本期营业收入1亿元，上年营业收入8000万元。')
        self.assertEqual([x['period'] for x in a], ['2022年', '2021年'])

    def test_comparison_does_not_change_next_field_year(self):
        a = self.fields('本期营业收入1亿元，较上年增长10%；净利润2000万元。')
        self.assertEqual([x['period'] for x in a], ['2022年', '2022年'])

    def test_qualified_profit_and_negative_unit(self):
        a = self.fields('本期扣非后归属于上市公司股东的净利润-2.5万元。')
        self.assertEqual(a[0]['field'], '扣非后归属于上市公司股东的净利润')
        self.assertEqual(a[0]['normalized_value'], '-25000.0')

    def test_earnings_per_share(self):
        a = self.fields('本期基本每股收益0.5元/股。')
        self.assertEqual(a[0]['normalized_unit'], '元/股')
        self.assertEqual(a[0]['normalized_value'], '0.5')

    def test_percentage_and_subject_offset(self):
        body = '本期资产负债率45%。'
        title = ' 测试公司:2022年年度报告'
        text = '报告：' + title + '\n正文：' + body
        a = numeric_annotations(text, title, body)[0]
        self.assertEqual(a['normalized_value'], '0.45')
        self.assertEqual(a['normalized_unit'], 'ratio')
        e = a['subject_evidence']
        self.assertEqual(text[e['start']:e['end']], '测试公司')

    def test_merged_party_profit_rejected(self):
        self.assertEqual(self.fields('本期被合并方在合并前净利润10万元。'), [])

    def test_missing_de_qualified_profit_preserved(self):
        a = self.fields('本期归属于上市公司股东净利润10万元。')[0]
        self.assertEqual(a['field'], '归属于上市公司股东净利润')

    def test_action_words_not_opinion_target(self):
        self.assertIsNone(clear_opinion('我们建议持续关注环境治理市场下沉机遇。'))

    def test_adjusted_profit_context_preserved(self):
        a = self.fields('本期剔除股份支付费用影响后,归属于上市公司股东的净利润10万元。')[0]
        self.assertEqual(a['measurement_basis'], '剔除股份支付费用影响后')

    def test_business_scope_preserved(self):
        a = self.fields('本期证券经纪业务营业收入10万元。')[0]
        self.assertIn('证券经纪业务', a['business_scope'])

    def test_semicolon_not_part_of_single_cause(self):
        self.assertIsNone(clear_causal('收入下降主要由于客户减少;另一业务收入持续增长。'))

    def test_historical_and_hypothetical_paragraph_rejected(self):
        self.assertEqual(self.fields('2020年营业收入1亿元。'), [])
        self.assertEqual(self.fields('本期预计营业收入1亿元。'), [])

    def test_long_cause_not_truncated(self):
        self.assertIsNone(clear_causal('公司利润增长主要系' + '市场需求持续扩大' * 30 + '。'))

    def test_correct_causal_direction(self):
        a = clear_causal('公司营业利润增长主要系销售规模持续扩大。')
        self.assertEqual(a['cause']['text'], '销售规模持续扩大')
        self.assertEqual(a['effect']['text'], '公司营业利润增长')

    def test_opinion_holder_and_target(self):
        a = clear_opinion('我们认为公司未来三年营业收入有望持续增长。')
        self.assertEqual(a['holder'], '报告作者')
        self.assertEqual(a['target'], '公司')
        self.assertEqual(a['forecast_time'], '未来三年')
        b = clear_opinion('我们预计公司2022-2024年归母净利润持续增长。')
        self.assertEqual(b['forecast_time'], '2022-2024年')

    def test_grammatical_phrase_is_not_target(self):
        self.assertIsNone(clear_opinion('我们认为一种可能性是市场流动性改善带来估值回升。'))

    def test_long_opinion_not_truncated(self):
        self.assertIsNone(clear_opinion('我们认为公司' + '营业收入持续增长' * 30 + '。'))


if __name__ == '__main__':
    unittest.main()
