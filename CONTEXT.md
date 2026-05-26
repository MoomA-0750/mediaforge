# MediaForge

A local web UI that wraps multiple CLI media tools (ffmpeg, ImageMagick, yt-dlp) and exposes them as a unified, browser-accessible interface running on the host machine.

## Language

### Tools and availability

**Tool**:
One of the supported CLI programs: ffmpeg, ImageMagick, or yt-dlp. A Tool lives on the host filesystem; the application never bundles or installs Tools itself.
_Avoid_: plugin, backend, engine

**Capability**:
A Tool that was confirmed present (via `shutil.which`) when the server started. Features that require a missing Capability are visible but disabled.
_Avoid_: feature flag, availability, support

**Capability Check**:
The one-time detection pass run at server startup that determines which Tools are present and records them as Capabilities.
_Avoid_: health check, probe, scan

### Work and processing

**Job**:
A single unit of work submitted to the queue: one input file, one operation, one output file. Every Tool produces Jobs; they share a common lifecycle (pending → running → done/error/cancelled).
_Avoid_: task, process, operation

**Batch**:
A set of Jobs submitted together by the user for the same operation applied to multiple input files. A Batch is a submission gesture, not a persistent entity — once submitted it dissolves into individual Jobs in the queue.
_Avoid_: bulk job, multi-job, group

**Job Type**:
The string identifier that determines which Tool and operation a Job runs (e.g. `convert`, `trim`, `image_resize`, `ytdlp_download`). Job Type is always scoped to a single Tool.
_Avoid_: operation type, command type

### UI concepts

**Feature**:
A user-facing operation within a tab (e.g. "Image Resize", "Video Convert", "Download"). Each Feature declares exactly one required Capability. If that Capability is absent, the Feature is visible but blocked by an Install Banner.
_Avoid_: function, tool (overloaded), action

**Install Banner**:
The UI element rendered inside a tab when its required Capability is absent. Shows the install command appropriate to the detected OS, with an escape hatch to see all package managers.
_Avoid_: error message, warning, disabled state

---

## Example dialogue

> **Dev**: I want to add a watermark feature for images.
>
> **Domain expert**: That's a new Feature in the Image tab. It requires ImageMagick as its Capability — same as Resize and Format Convert. If ImageMagick isn't installed, all three Features show the Install Banner together.
>
> **Dev**: And when the user uploads ten images and hits "Resize All"?
>
> **Domain expert**: That's a Batch submission. Ten Jobs land in the queue immediately, each with its own progress and status. There's no "Batch" object after that — just ten Jobs the user can cancel individually.
>
> **Dev**: What if they restart the server and ImageMagick is now installed?
>
> **Domain expert**: The Capability Check reruns on startup and ImageMagick becomes a Capability. The Install Banner disappears and the Features become active. Jobs from the previous session are gone — they're in-memory only.
