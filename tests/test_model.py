from kicker_tracker.analysis import points_for_attempt, robust_mean
from kicker_tracker.report import build_html

def test_fantasy_scoring():
    assert points_for_attempt(39,True)==3
    assert points_for_attempt(40,True)==4
    assert points_for_attempt(49,True)==4
    assert points_for_attempt(50,True)==5
    assert points_for_attempt(62,False)==-1

def test_robust_outlier():
    assert robust_mean([25,3,3,3,3]) < 7.4
    assert robust_mean([9,10,8,9,9])==9

def test_report_handles_empty():
    html=build_html([],{'season':2026,'target_week':9,'as_of':'2026-11-03'})
    assert 'Week 9' in html and 'McPherson' not in html
