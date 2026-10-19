from pathlib import Path
import json
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd

# Prefer Bitter when available; otherwise use Matplotlib's bundled font.
font_dir = Path.home() / 'Library/Fonts'
bitter_fonts = [
    font_dir / 'Bitter-Regular-Static.ttf',
    font_dir / 'Bitter-Bold-Static.ttf',
]

if all(font.exists() for font in bitter_fonts):
    for font in bitter_fonts:
        font_manager.fontManager.addfont(str(font))

    font_family = 'Bitter'
else:
    font_family = 'DejaVu Sans'
    print('Bitter fonts not found; using DejaVu Sans.')

plt.rcParams.update({
    'font.family': font_family,
    'font.weight': 'normal',
    'axes.titleweight': 'normal',
    'axes.labelweight': 'normal',
})

INPUT = Path('analysis/vocabulary/news/vocabulary_categories.csv')
DICTIONARY = Path('analysis/vocabulary/dictionary.json')
OUTPUT = Path('analysis/vocabulary/news/autonomy_vocabulary_v1.png')

categories = ['openness', 'control', 'sovereignty']
df = pd.read_csv(INPUT)
df = df[(df['period'] < '2026-Q4') & (df['group'] == 'autonomy') &
        (df['category'].isin(categories))]
pivot = df.pivot(index='period', columns='category', values='per_1000_words').sort_index()

fig, ax = plt.subplots(figsize=(11, 5.5))
for category in categories:
    ax.plot(pivot.index, pivot[category], marker='o', linewidth=2,
            label=category.capitalize())
ax.set_title('Autonomy-related vocabulary in Mistral AI news articles (2023–2026)',
             loc='left', pad=18)
ax.set_ylabel('Matched token positions per 1,000 words')
ax.set_ylim(bottom=0)
ax.tick_params(axis='x', rotation=45)
ax.grid(axis='y', alpha=0.25)
ax.legend(frameon=False)

# Fix the plot region explicitly; annotations below won't affect its placement.
fig.subplots_adjust(left=0.09, right=0.98, top=0.90, bottom=0.49)

with DICTIONARY.open(encoding='utf-8') as f:
    dictionary = json.load(f)

left, font_size = 0.10, 11
fig.text(left, 0.32, 'Dictionary terms:', fontsize=font_size, va='top')

# Render bold Bitter labels and regular Bitter terms as separate text artists.
# Measuring label width ensures that terms begin directly after each label.
fig.canvas.draw()
renderer = fig.canvas.get_renderer()
figure_width_px = fig.bbox.width

def dictionary_line(category, y, terms, continuation=None):
    label = fig.text(left, y, category.capitalize() + ':', fontsize=font_size,
                     fontweight='bold', va='top')
    label_width = label.get_window_extent(renderer=renderer).width / figure_width_px
    term_x = left + label_width + 0.006
    fig.text(term_x, y, terms, fontsize=font_size, va='top')
    if continuation:
        fig.text(term_x, y - 0.042, continuation, fontsize=font_size, va='top')

open_terms = ', '.join(dictionary['autonomy']['openness'])
control_terms = dictionary['autonomy']['control']
sovereign_terms = ', '.join(dictionary['autonomy']['sovereignty'])
# Split at a term boundary, rather than wrapping text inside an offset box.
control_first = ', '.join(control_terms[:10]) + ','
control_second = ', '.join(control_terms[10:])

dictionary_line('openness', 0.27, open_terms)
dictionary_line('control', 0.22, control_first, control_second)
dictionary_line('sovereignty', 0.125, sovereign_terms)

fig.text(left, 0.035,
         'Source: Dictionary-based analysis of 89 Mistral AI news articles '
         '(2023-Q3–2026-Q3). Quarterly article counts vary.',
         fontsize=9.5, va='bottom')

OUTPUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUTPUT, dpi=200)
print(f'Saved: {OUTPUT}')
