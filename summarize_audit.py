import csv
from collections import Counter, defaultdict

IN = 'low_confidence_audit.csv'
OUT = 'low_confidence_summary.txt'
OUT_CSV = 'low_confidence_top50.csv'

per_label = defaultdict(Counter)
overall = Counter()
rows = []
with open(IN, newline='', encoding='utf-8') as fh:
    reader = csv.DictReader(fh)
    for r in reader:
        label = r['label']
        snippet = r['snippet'].strip()
        # normalize snippet (shorten for counting)
        key = ' '.join(snippet.split())[:200]
        per_label[label][key] += 1
        overall[key] += 1
        rows.append(r)

with open(OUT, 'w', encoding='utf-8') as out:
    out.write('Low-confidence audit summary\n')
    out.write('Total low-conf candidates: %d\n\n' % len(rows))
    for label, counter in per_label.items():
        out.write('Label: %s  (count=%d)\n' % (label, sum(counter.values())))
        for k, v in counter.most_common(20):
            out.write('  %4d  %s\n' % (v, k.replace('\n', ' ')))
        out.write('\n')

    out.write('\nOverall top 50 snippets:\n')
    for k, v in overall.most_common(50):
        out.write('  %4d  %s\n' % (v, k.replace('\n', ' ')))

# write top 50 overall to CSV
with open(OUT_CSV, 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    w.writerow(['count','snippet'])
    for k, v in overall.most_common(50):
        w.writerow([v, k])

print('Wrote', OUT, 'and', OUT_CSV)
