# Paper → video automation

In-process scheduler that fetches trending GenAI papers, runs the Studio
pipeline, and packages every artifact into one folder named after the paper.

## Sources (`AUTO_SOURCE`)

| Value | Behavior |
|-------|----------|
| `trending` (default) | Hugging Face Daily Papers + arXiv GenAI keywords + Semantic Scholar bulk |
| `hf` | Hugging Face Daily Papers only |
| `arxiv` | arXiv Atom API (categories + GenAI keyword filter) |
| `semantic_scholar` | Semantic Scholar `/paper/search/bulk` (publicationDate sort) |

## Output layout

```
automation_output/
  seen.json
  last_run.json
  schedule_fired.json
  YYYYMMDD_<title-slug>_<arxivId>/
    paper.json               # includes pdf_file = "<title-slug>_<id>.pdf"
    <title-slug>_<id>.pdf    # source PDF (named after the paper — not paper.pdf)
    post.txt                 # primary social post (from long-form metadata)
    results.json             # job ids + render summary
    video/
      video.mp4
      thumbnail.png
      presentation.html
      narration.txt
      post.txt
      metadata.json
      audio/
      pages/
    reel/                    # same shape for short-form
```

Legacy folders may still have ``paper.pdf`` and flat ``video_video.mp4`` copies;
new runs use the named PDF and keep everything under ``video/`` + ``reel/`` only.

## Schedule

Default slots: **01:00** and **19:00** local time (outside the 09–18 working-hours
block). The previous default `13` was always skipped by that block.
