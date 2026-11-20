# Vision, personas and use cases

## Purpose

kata is a self-hosted learning companion for people who already know a lot and need to learn
adjacent material fast. It keeps a model of what each learner knows, reads the lesson or
document the learner has open, and shows within about 30 seconds which parts are new. It
advises inside the learner's own projects and turns knowledge gaps into short practice
courses.

The quality it aims for is responsiveness and context awareness: speed and knowing what the
learner is looking at, not voice or entertainment.

## Who it is for

**Primary persona: an experienced engineer learning adjacent stacks under a time limit.**
They have years of practice in one stack, a fixed window (a course, a project deadline, a
career change) and more material than time. Much of the material repeats what they know.
Their problem is not access to content but triage: what to skip, what to skim, what to learn
deeply.

Secondary personas:

- **A small group sharing one installation** (a household, a team, a study group). Each person
  has a private profile; the people running it are few and trusted.
- **A self-taught practitioner** working through books, documentation and videos with no
  syllabus, who wants gaps found from their own code and notes.
- **A course participant** with a fixed syllabus and exams, who wants the tool to respect the
  course's rules on AI use.

## Principles

1. **Assistant first, not a drill machine.** Practice is generated from gaps on request.
   There is no global review calendar.
2. **Own infrastructure first.** The core runs on the user's own machine or server. Local
   models run on the users' own machines as workers that connect out to the core. Cloud models
   are a fallback.
3. **Clients never wait.** Short timeout, then the cache; nothing blocks the learner.
4. **Provider-agnostic.** Any model provider through adapters, including local runtimes.
5. **Ready for several devices and a server from day one**, behind a replaceable
   authentication layer.
6. **The repository contains code only.** No study material, no personal or learner data.
7. **The companion helps the learner and does not replace them.** It asks them to try first
   and stays silent on graded assessments.

## Use cases

| ID | Name | Description |
|----|------|-------------|
| S1 | Lesson scan | The learner opens a lesson. In about 30 seconds a side-panel card shows which blocks are new, learning or known; the page highlights new blocks strongly and known blocks faintly. |
| S2 | Project advice | In the editor, the companion uses project structure and the knowledge model to point at gaps, suggest improvements in terms of concepts the learner knows (with analogies from stacks they know), suggest practice, and warn about risks such as secrets in code. |
| S3 | Terminal learning | The learner starts a tracked terminal session (local shell or SSH). Commands, exit codes and timing are recorded; repeated errors trigger a nudge or a lesson. Tracking is opt-in per session. |
| S4 | Gap to mini-course | The learner picks categories and topics from their gaps and gets a short practice course built in the trainer tool. Results return into the knowledge model. |
| S5 | Ask anything | Questions about the current page, lesson or project, with context supplied automatically. |
| S6 | Triage a syllabus | The learner imports a syllabus or skill list. Each module gets an action: test out, speed up, learn deeply, or skim. |
| S7 | Plan within a time budget | Several learning tracks share one time budget. Each track has a deadline; some decisions (such as choosing a specialization) are deliberately deferred to a decision point. |

## Requirements implied by the use cases

- **Skill import.** A starting skill list (a file, or a syllabus) is the first hypothesis of
  what the learner knows; tests, the "I know this" button and normal use refine it.
- **Known vs new triage.** Every block or module is classified known, learning or new. The
  label is computed in code from the topic and the learner's profile; a model only picks the
  topic.
- **Time-boxed tracks.** Tracks carry a deadline and share a single time budget. Tracks and
  triage actions are data, not hard-coded.
- **Evidence from the learner's own artifacts.** Knowledge is inferred from tests, reading,
  the learner's code and notes, and explicit marks. Each learning block ends in a showable
  artifact the learner produced.
- **Gap-driven practice.** Practice is chosen from the gap between what a goal requires and
  what the learner's evidence shows, including projects that exercise operational skills, not
  only exercises.
- **Per-user cost caps.** Cloud spend is tracked per call and capped per user per month, with
  a warning at 80 percent and a hard stop at the cap, enforced in the core. Subscription and
  API billing are separate products; the application uses API keys through its adapters.
- **Content-source constraints.** Some course platforms forbid downloading material. The tool
  reads a page only when the learner has it open and never crawls or bulk-downloads
  restricted sources. Open public material may be fetched, respecting robots.txt and site
  terms.
- **Configurable AI-use policy.** Courses and exams differ in what AI help is allowed. The tool
  stays silent on graded pages by default and offers an exam mode that disables or restricts
  AI features.
- **Practice in the learner's own terminal.** Hands-on labs often run on remote machines
  reached over SSH. The tool provides a terminal-friendly practice path, not only a browser
  panel.
- **Resource-aware local models.** A local model shares its GPU with other workloads. The
  worker yields to foreground requests and can unload models on demand.
- **Responsive and offline-tolerant.** See the targets in [`design/architecture.md`](design/architecture.md).
