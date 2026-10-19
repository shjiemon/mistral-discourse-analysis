# Methodology

## Research approach

This repository supports *Mistral AI: Rethinking Technological Autonomy through Infrastructural Dependence*, addressing the question:

> How has Mistral AI's proposition of greater technological autonomy for those using its technology evolved since its founding, and how is this proposition shaped by infrastructural dependence?

The research adopts a **technographic approach**, examining technological offerings and infrastructural arrangements through publicly available documentation and other empirical traces.

An exploratory vocabulary analysis complements this approach by tracing changes in Mistral's public communications. It distinguishes between the **autonomy promised to users** and **Mistral's own infrastructural dependencies**. Vocabulary frequencies indicate discursive emphasis, not actual degrees of technological autonomy.

## Corpus construction

The primary corpus contains **90 English-language articles** collected from Mistral's official news website, covering September 2023–October 2026.

The collector (`scripts/collect.py`) discovers URLs through the news overview and sitemaps. It preserves retrieved HTML, extracted Markdown and plain text, and publication metadata.

The **Wayback Machine** was consulted to assess historical coverage and investigate the appearance of sovereignty-related corporate webpages. Individual news articles were not systematically compared with archived versions.

Four supplementary corporate webpages were captured using SingleFile on **October 19, 2026**: *Why Sovereign AI*, *Products*, *Our Method*, and *Sovereign AI in Practice*. Their text was extracted using `scripts/extract_corporate_pages.py`.

These pages were observed in the Wayback investigation by approximately October 6, 2026, but their exact publication dates are unknown. The captured wording cannot be assumed to date from their first appearance.

Corporate webpages are treated separately from dated news articles because they differ in purpose and may be updated independently.

## Vocabulary analysis

A manually constructed dictionary (`analysis/vocabulary/dictionary.json`) contains **121 entries** across ten categories:

| Autonomy-related | Technology-related |
|---|---|
| Openness | Infrastructure |
| Choice | Access/distribution |
| Control | Customization |
| Independence/autonomy | Performance |
| Sovereignty | Products |

The analysis (`scripts/analyze_vocabulary_timeline.py`) matches case-insensitive token sequences, including multiword expressions. It records term occurrences, document prevalence, and category frequencies.

To avoid double-counting overlapping dictionary entries, category frequencies count unique matched token positions. Results are normalized per 1,000 tokens and aggregated quarterly for historical comparison.

The script supports three corpus configurations: `news`, `corporate`, and `expanded` (both combined).

The principal visualization (`scripts/plot_vocabulary_timeline.py`) uses the news-only corpus and compares **openness, control, and sovereignty** from 2023-Q3 through 2026-Q3. The incomplete 2026-Q4 period, containing one news article, is excluded.

## Interpretation and limitations

Vocabulary patterns help identify changes in Mistral's public positioning and periods warranting closer qualitative investigation.

These findings inform the broader technographic analysis of model licensing, deployment options, cloud infrastructure, computing resources, and commercial partnerships.

Important limitations include:

- **Corpus coverage:** The collected articles may not represent all relevant Mistral publications.
- **Historical stability:** Retrieved articles may have changed since their original publication.
- **Extraction accuracy:** Automated extraction may omit or include unwanted text.
- **Dictionary sensitivity:** Results depend on selected terms and do not account for their meanings in context.
- **Temporal variation:** Article frequency, length, and subject matter vary between periods.
- **Genre differences:** News articles and corporate webpages are not directly equivalent.

Changes in vocabulary therefore cannot independently establish changes in technological autonomy, infrastructural dependence, or their causes.

## Reproducibility

The repository preserves source HTML, extracted texts, the dictionary, analysis scripts, and generated results.

To reproduce the vocabulary analysis:

```bash
python -m pip install -r requirements.txt

python scripts/analyze_vocabulary_timeline.py --corpus news --output analysis/vocabulary/news
python scripts/analyze_vocabulary_timeline.py --corpus corporate --output analysis/vocabulary/corporate
python scripts/analyze_vocabulary_timeline.py --corpus expanded --output analysis/vocabulary/expanded
```

Use the preserved corpus rather than recollecting live webpages, which may have changed.

See `README.md` for additional instructions.