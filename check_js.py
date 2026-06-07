with open('/opt/auctioneer/static/index.html', 'r') as f:
    html = f.read()
import re
m = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
if m:
    js = m.group(1)
    print('Braces diff:', js.count('{') - js.count('}'))
    print('Parens diff:', js.count('(') - js.count(')'))
    print('QUESTION_BANK count:', js.count('QUESTION_BANK'))
    print('Q func calls:', js.count("Q('"))
    if 'let appState' in js:
        print('appState declared: YES')
    else:
        print('appState declared: NO')
    for fn in ['applyFilters','renderQuestions','getFilteredQuestions','init','login','logout']:
        print(fn + ': ' + ('YES' if ('function ' + fn) in js else 'NO'))
    # Check the transition from question data to API layer
    idx = js.find('QUESTION_BANK.push')
    if idx > 0:
        print('Last push at char:', idx)
        print('Context:', js[idx:idx+100])
