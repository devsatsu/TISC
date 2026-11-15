import json, unittest
from pathlib import Path
from field_extractor import extract, parse_value
class ExtractionTests(unittest.TestCase):
 def run_case(self,texts):
  boxes=[{'id':str(i),'text':t,'bbox':[x,0,x+width,15],'confidence':None} for i,(t,x,width) in enumerate(texts)]
  return extract({'source_photo':'synthetic','boxes':boxes},json.loads(Path('lookups/ape_bill_v1.json').read_text()))[0]
 def test_combined(self): self.assertEqual(self.run_case([('NET BILL: -123.45',0,120)])['net_payable']['value'],'-123.45')
 def test_separate(self): self.assertEqual(self.run_case([('NET BILL',0,70),('123.45',80,50)])['net_payable']['value'],'123.45')
 def test_meter(self): self.assertEqual(self.run_case([('PRES KWH',0,80),('321 01-02-2026 1',90,130)])['present_kwh']['value'],'321')
 def test_missing(self): self.assertEqual(self.run_case([('NET BILL',0,70)])['net_payable']['status'],'label_found_value_unreadable')
 def test_competing(self): self.assertEqual(self.run_case([('NET BILL',0,70),('10',80,15),('20',110,15)])['net_payable']['status'],'ambiguous_match')
 def test_split(self): self.assertEqual(self.run_case([('NET',0,25),('BILL',30,30),('12',70,20)])['net_payable']['value'],'12')
 def test_date(self): self.assertEqual(parse_value('15-11-2026','date'),'2026-11-15')
 def test_date_is_not_reading(self): self.assertIsNone(self.run_case([('PRES KWH',0,80),('01-02-2026',90,130)])['present_kwh']['value'])
 def test_invalid_date(self):
  with self.assertRaises(ValueError): parse_value('31-02-2026','date')
if __name__=='__main__': unittest.main()
