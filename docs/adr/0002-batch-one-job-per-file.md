# Batch processing submits one Job per file

When a user submits a Batch (multiple images for the same ImageMagick operation), each input file becomes an independent Job in the queue. There is no persistent Batch entity.

The obvious alternative is a single Job that runs `mogrify` across all files at once. `mogrify` is simpler to invoke but gives no per-file progress, no per-file cancellation, and fails silently on individual files without surfacing which ones. Splitting into one Job per file means each file gets its own progress bar, can be cancelled independently, and surfaces errors at the right granularity. The trade-off is that a large Batch floods the queue list; this is acceptable because the Queue tab already supports filtering by Tool, and future grouping UI can address it without changing the underlying Job model.
