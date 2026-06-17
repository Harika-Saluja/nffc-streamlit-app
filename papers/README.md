# Papers & references

Shared sports-analytics reading for the projects. Drop PDFs in this folder and
add a row to the relevant table below.

**Filing convention:** lowercase, hyphenated — `author-year-keywords.pdf`
(e.g. `spearman-2018-pitch-control.pdf`).

## How to add a paper

1. Save the PDF here with the naming convention above (or just link it if it's a web resource).
2. Add a row under the matching project (or **General**) with a one-line "why it's relevant".

## General / cross-project

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| _add papers here_ | | | | | |

---

## Per project

Sections follow the picked projects in [`../projects/README.md`](../projects/README.md).

### Project 1 — Injury Risk Modelling

Core reading for GPS/workload-based injury forecasting and the anomaly-detection /
baseline framing in the brief. Several injury-prediction PDFs already exist in the
club's reading collection (the sibling `NFFC-UoB-Research/Papers` repo — ask the
supervisor to copy them across): Huth 2025, Freitas 2025, Martins 2024 (review),
Leckey 2024 (review), Everett 2024, Mateus 2025 (AI-in-sport review).

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Effective injury forecasting in soccer with GPS training data and machine learning | Rossi et al. | 2018 | GPS + ML injury forecasting | Closest analogue to this project — features from training GPS, interpretable ML | [PLoS ONE](https://doi.org/10.1371/journal.pone.0201264) |
| The training–injury prevention paradox (ACWR / workload) | Gabbett | 2016 | Workload–injury relationship | Foundation for acute:chronic workload features and load-spike reasoning | [BJSM](https://doi.org/10.1136/bjsports-2015-095788) |
| A preventive model for muscle injuries: a novel approach based on learning algorithms | López-Valenciano et al. | 2018 | ML injury risk classification | Demonstrates (and cautions on) ML injury classification with modest sample sizes | [Med Sci Sports Exerc](https://doi.org/10.1249/MSS.0000000000001535) |
| Machine learning for injury risk (scoping review) | Leckey et al. | 2024 | Review of ML injury methods | Surveys tree-based / common approaches; good methods orientation | _from club collection_ |
| _add as you read_ | | | | | |

> **Brief framing:** injury prediction is hard at these sample sizes. The
> recommended angles are (a) **transfer learning** game tracking → training GPS,
> and (b) **unsupervised anomaly detection / time-series** on physical output to
> flag spikes/dips that precede soft-tissue injuries — i.e. model physiological
> baselines rather than predict injuries directly. Labels come from
> `injuries/gb1_injuries_with_mapping.*` in the bucket; weekly availability proxy
> from the FPL archive (`minutes`). See `docs/external_data.md`.

### Project 2 — Career Trajectory / Experience Analysis
| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| | | | | | |

### Project 4 — Team Styles: Sequence Clustering & Similarity
| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| | | | | | |

### Project 6 — What is a "perfect" signing?
| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| | | | | | |

### Project 7 — Pitch Control & Expected Threat Modelling

The core literature for spatial control + value layers (xT / EPV), plus the
open-data tutorials the student can build on **before** club data access lands.

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Wide Open Spaces: measuring space creation in professional soccer | Fernández & Bornn | 2018 | Pitch control model | Foundational pitch-control / space-occupation surface from tracking | [MIT Sloan PDF](https://www.lukebornn.com/papers/fernandez_sloan_2018.pdf) |
| Beyond Expected Goals | Spearman | 2018 | Off-ball scoring opportunity via pitch control | Builds a scoring-opportunity value on top of pitch control | [MIT Sloan PDF](https://www.sloansportsconference.com/research-papers/beyond-expected-goals) |
| Physics-Based Modeling of Pass Probabilities in Soccer | Spearman, Basye, Dick, Hotovy, Pop | 2017 | Pass / control probability | The pass-probability model under most pitch-control implementations | [MIT Sloan PDF](https://www.sloansportsconference.com/research-papers/physics-based-modeling-of-pass-probabilities-in-soccer) |
| A framework for the fine-grained evaluation of the instantaneous expected value of soccer possessions (EPV) | Fernández, Bornn & Cervone | 2021 | Expected Possession Value | The EPV layer to put on top of pitch control | [Machine Learning (Springer)](https://link.springer.com/article/10.1007/s10994-021-05989-6) |
| Introducing Expected Threat (xT) | Singh (Karun) | 2019 | Expected Threat grid | Accessible xT formulation; good baseline value layer from event data | [karun.in blog](https://karun.in/blog/expected-threat.html) |
| Friends of Tracking — pitch control tutorials & code | Shaw (Laurie) et al. | 2020 | Pitch control from tracking (hands-on) | Tutorial videos + `LaurieOnTracking` code; ideal starting point | [YouTube](https://www.youtube.com/c/FriendsofTracking) · [GitHub](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking) |
| Metrica Sports sample tracking data | Metrica Sports | 2020 | Open tracking dataset | Free tracking data to prototype on; frame shape ≈ our SecondSpectrum data | [GitHub](https://github.com/metrica-sports/sample-data) |

> **Tip for the spatial-control student:** the SecondSpectrum frame format
> (per-player `xyz` + `speed`, ball position, 25 fps) maps closely onto the
> Metrica / Friends-of-Tracking public data. Build and validate the pitch-control
> + xT pipeline on public tracking first, then repoint it at `nffc_data.ssio`
> when the club data and read-only key are available.

### Project 8 — Automated Set-Piece Clustering
| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| | | | | | |
