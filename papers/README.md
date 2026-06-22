# Papers & references

Shared sports-analytics reading for the projects. Drop PDFs in this folder and
add a row to the relevant table below.

**Filing convention:** lowercase, hyphenated — `author-year-keywords.pdf`
(e.g. `spearman-2018-pitch-control.pdf`).

## How to add a paper

1. Save the PDF here with the naming convention above (or just link it if it's a web resource).
2. Add a row under the matching project (or **General**) with a one-line "why it's relevant".

## Collection hubs

Curated, regularly-updated roundups of the football-analytics field — great for
finding more papers, code and blogs beyond the lists below:

- **Jan Van Haaren — Soccer Analytics Reviews** (annual literature/resource roundups, 2020–2025): [2024 review](https://www.janvanhaaren.be/posts/soccer-analytics-review-2024/) · [resources index](https://www.janvanhaaren.be/resources.html)
- **Edd Webster — `football_analytics`** (curated community resource list + data/docs): [github.com/eddwebster/football_analytics](https://github.com/eddwebster/football_analytics)
- **Jake Kolliari (jakeyk11) — `football-data-analytics`** (tools, viz, a pass-clustering model) + portfolio: [github.com/jakeyk11/football-data-analytics](https://github.com/jakeyk11/football-data-analytics) · [jakeyk11.github.io](https://jakeyk11.github.io/)

## General / cross-project

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| A public data set of spatio-temporal match events in soccer competitions | Pappalardo et al. | 2019 | Open event dataset | Large public events dataset; good for prototyping | [Scientific Data](https://doi.org/10.1038/s41597-019-0247-7) |
| Actions Speak Louder than Goals: Valuing Player Actions in Soccer (VAEP) | Decroos, Bransen, Van Haaren, Davis | 2019 | Action valuation | Core possession-value framework used across projects | [KDD](https://doi.org/10.1145/3292500.3330758) |
| Unlocking the potential of big data to support tactical performance analysis (systematic review) | Goes et al. | 2021 | Tactical analytics review | Survey bridging sports science + CS methods | [EJSS](https://doi.org/10.1080/17461391.2020.1747552) |
| Soccermatics: Mathematical Adventures in the Beautiful Game (book) | Sumpter | 2016 | Accessible primer | Good conceptual grounding | [Bloomsbury](https://www.bloomsbury.com/uk/soccermatics-9781472924124/) |
| socceraction (xT + VAEP) | ML-KULeuven | — | Python library | Event→SPADL, xT/VAEP implementations | [GitHub](https://github.com/ML-KULeuven/socceraction) |
| kloppy | PySport | — | Python library | Vendor-independent tracking/event model; **supports SecondSpectrum** | [kloppy.pysport.org](https://kloppy.pysport.org/) |
| mplsoccer | Rowlinson | — | Python library | Pitch plotting + StatsBomb open-data loaders | [docs](https://mplsoccer.readthedocs.io/) |
| StatsBomb Open Data | StatsBomb | — | Open event data | Free events for prototyping | [GitHub](https://github.com/statsbomb/open-data) |
| Friends of Tracking | Friends of Tracking | 2020 | Tutorials + code | Hands-on tracking-data analytics | [GitHub](https://github.com/Friends-of-Tracking-Data-FoTD) |
| MIT Sloan Sports Analytics Conference — research papers | MIT Sloan | — | Paper hub | Primary venue for applied football analytics | [research papers](https://www.sloansportsconference.com/research-papers) |

---

## Per project

Sections follow the picked projects in [`../projects/README.md`](../projects/README.md).

### Project 1 — Injury Risk Modelling

Core reading for GPS/workload-based injury forecasting and the anomaly-detection /
baseline framing in the brief.

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Effective injury forecasting in soccer with GPS training data and machine learning | Rossi et al. | 2018 | GPS + ML injury forecasting | Closest analogue to this project — features from training GPS, interpretable ML | [PLoS ONE](https://doi.org/10.1371/journal.pone.0201264) |
| The training–injury prevention paradox (ACWR / workload) | Gabbett | 2016 | Workload–injury relationship | Foundation for acute:chronic workload features and load-spike reasoning | [BJSM](https://doi.org/10.1136/bjsports-2015-095788) |
| A preventive model for muscle injuries: a novel approach based on learning algorithms | López-Valenciano et al. | 2018 | ML injury risk classification | Demonstrates (and cautions on) ML injury classification with modest sample sizes | [Med Sci Sports Exerc](https://doi.org/10.1249/MSS.0000000000001535) |
| Predicting noncontact injuries of professional football players using ML | Freitas et al. | 2025 | GPS + ML injury prediction | Recent SVM model; player-specific features | [PLoS ONE](https://doi.org/10.1371/journal.pone.0315481) |
| Acute:chronic workload ratio for predicting sports injury risk: systematic review & meta-analysis | Qin, Li, Chen | 2025 | Workload / ACWR critique | Questions ACWR predictive power alone | [BMC SSMR](https://doi.org/10.1186/s13102-025-01332-x) |
| An overview of machine learning applications in sports injury prediction | Amendolara et al. | 2023 | ML injury review | 42 papers; flags data-size/standardisation issues | [Cureus](https://doi.org/10.7759/cureus.46170) |
| Epidemiology of injuries in professional football (systematic review & meta-analysis) | López-Valenciano et al. | 2020 | Injury epidemiology | Base rates; match vs training; lower-limb dominant | [BJSM](https://doi.org/10.1136/bjsports-2018-099577) |
| A novel approach for sports injury risk prediction: time-series image encoding + deep learning | Ye et al. | 2023 | Time-series / DL | Supports the anomaly / time-series angle | [Front. Physiol.](https://doi.org/10.3389/fphys.2023.1174525) |
| Sports injury risk prediction via temporal graph encoding + GNNs: a cross-sport transfer-learning framework | Nature Sci. Rep. | 2025 | Transfer learning | Directly addresses the transfer-learning angle | [Sci Rep](https://www.nature.com/articles/s41598-025-21613-2) |
| The Strain of Success: a predictive model for injury risk mitigation and team success in soccer | Everett et al. | 2024 | Injury-aware team selection | MDP + MCTS balancing performance vs injury; ~13% fewer first-team injuries (also relevant to Project 6) | [arXiv](https://arxiv.org/abs/2402.04898) |
| _add as you read_ | | | | | |

> **Brief framing:** injury prediction is hard at these sample sizes. The
> recommended angles are (a) **transfer learning** game tracking → training GPS,
> and (b) **unsupervised anomaly detection / time-series** on physical output to
> flag spikes/dips that precede soft-tissue injuries — i.e. model physiological
> baselines rather than predict injuries directly. Injury labels come from
> `injuries/gb1_injuries_with_mapping.*` in the bucket (see the data dictionary).

### Project 2 — Career Trajectory / Experience Analysis

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| When do soccer players peak? A note | Dendir | 2016 | Peak age by position | Forwards ~25, defenders ~27 | [JSA](https://doi.org/10.3233/JSA-160021) |
| Estimation of player aging curves using regression and imputation | Schuckers, Lopez, Macdonald | 2023 | Aging-curve methodology | Delta method + selection-bias fix; code available | [Annals of OR](https://doi.org/10.1007/s10479-022-05127-y) |
| Establishing 'normal' career longevity in professional footballers | Jones et al. | 2025 | Career survival analysis | Kaplan–Meier longevity baselines | [KSSTA](https://doi.org/10.1002/ksa.12722) |
| Are soccer players older now than before? Aging trends & market value (UEFA CL) | Front. Psychol. | 2019 | Aging trends + value | Position-specific aging vs market value | [Front. Psychol.](https://doi.org/10.3389/fpsyg.2019.00076) |
| Acceleration and sprint profiles by playing position | Oliva-Lozano et al. | 2020 | Positional physical profile | Position-specific physical output | [PLoS ONE](https://doi.org/10.1371/journal.pone.0236959) |
| Artificial neural networks and player recruitment in professional soccer | Barron et al. | 2018 | ML on trajectories | Predicts career level from performance | [PLoS ONE](https://doi.org/10.1371/journal.pone.0205818) |
| PlayeRank: data-driven performance evaluation and player ranking | Pappalardo et al. | 2019 | Performance rating | A trajectory target metric | [ACM TIST](https://doi.org/10.1145/3343172) |
| Actions Speak Louder than Goals (VAEP) | Decroos et al. | 2019 | Action value | Alternative trajectory target | [KDD](https://doi.org/10.1145/3292500.3330758) |
| Ranking soccer teams on the basis of their current strength (MLE approaches) | Ley, Van de Wiele, Van Eetvelde | 2017 | League/team strength | Basis for league-difficulty / "experience" weighting | [arXiv](https://arxiv.org/abs/1705.09575) |
| _add as you read_ | | | | | |

### Project 4 — Team Styles: Sequence Clustering & Similarity

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Searching for a Unique Style in Soccer | Gyarmati, Kwak, Rodriguez | 2014 | Passing motifs | Foundational flow-motif style fingerprinting | [arXiv](https://arxiv.org/abs/1409.0308) |
| Flow motifs in soccer: what can passing behavior tell us? | Bekkers, Dabadghao | 2019 | Passing-sequence motifs | Motif-based team/player style | [JSA](https://doi.org/10.3233/JSA-190290) |
| Automatic Discovery of Tactics in Spatio-Temporal Soccer Match Data | Decroos, Van Haaren, Davis | 2018 | Tactic clustering | Clusters tactical patterns from data | [KDD](https://doi.org/10.1145/3219819.3219832) |
| Influence of contextual variables on styles of play in soccer | Fernández-Navarro et al. | 2018 | Style taxonomy | Direct play / counterattack / build-up styles | [IJPAS](https://doi.org/10.1080/24748668.2018.1479925) |
| Evaluating the effectiveness of styles of play in elite soccer | Fernández-Navarro et al. | 2019 | Style effectiveness | Outcome value of styles | [Proc. IMechE P](https://doi.org/10.1177/1747954119855361) |
| Using Dynamic Time Warping to Find Patterns in Time Series | Berndt, Clifford | 1994 | DTW method | Foundational DTW (sequence/possession clustering) | [AAAI WS PDF](https://cdn.aaai.org/Workshops/1994/WS-94-03/WS94-03-031.pdf) |
| Player Vectors: Characterizing Soccer Players' Playing Style | Decroos, Davis | 2020 | Style representation (NMF) | NMF style vectors capturing *spatial* style; similarity | [ECML PKDD](https://doi.org/10.1007/978-3-030-46133-1_34) |
| SoccerMix: representing soccer actions with mixture models | Decroos, Van Roy, Davis | 2020 | Soft clustering of actions | Mixture-model "soft" style clustering by location + direction; [code](https://github.com/ML-KULeuven/soccermix) | [ECML PKDD](https://doi.org/10.1007/978-3-030-67670-4_28) |
| Effective and efficient sports play retrieval with deep representation learning (play2vec) | Wang, Long, Cong, Ju | 2019 | Deep sequence embedding | Embeds play *sequences* from tracking (skip-gram + denoising encoder-decoder); [code](https://github.com/zhengwang125/play2vec) | [KDD](https://doi.org/10.1145/3292500.3330927) |
| Neural Discrete Representation Learning (VQ-VAE) | van den Oord, Vinyals, Kavukcuoglu | 2017 | Discrete deep representations | Foundational discrete-latent method — promising, under-applied for tactical "vocabularies" | [arXiv](https://arxiv.org/abs/1711.00937) |
| Unlocking the potential of big data (tactical review) | Goes et al. | 2021 | Tactical methods review | Method survey | [EJSS](https://doi.org/10.1080/17461391.2020.1747552) |
| Pass-clustering model (applied, code) | Kolliari (jakeyk11) | — | Applied clustering | 5M+ passes → 65 clusters; reference implementation | [GitHub](https://github.com/jakeyk11/football-data-analytics) |
| _add as you read_ | | | | | |

> **Techniques — how style analysis has evolved (a steer for this project):**
> early work used aggregated/positional stats and passing networks.
> **Non-negative matrix factorisation** (Player Vectors) was notable for capturing
> *spatial* differences in style from heatmaps rather than aggregated counts;
> **SoccerMix** extends this with soft, mixture-model clustering of actions by
> location and direction. The field has since shifted toward **sequences** —
> passing motifs, DTW-based clustering, and deep sequence embeddings (play2vec).
> A promising but (as far as we've seen) **under-applied** direction is **discrete
> deep representation learning** — VQ-VAE-style models, or deep/hierarchical
> HMMs — to learn a compact "vocabulary" of tactical states/sequences. A strong
> novel angle if the team wants one.

### Project 6 — What is a "perfect" signing?

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Beyond crowd judgments: data-driven estimation of market value in association football | Müller, Simons, Weinmann | 2017 | Market-value model | Seminal data-driven valuation; transfer-fee benchmark | [EJOR](https://doi.org/10.1016/j.ejor.2017.05.005) |
| Actions Speak Louder than Goals (VAEP) | Decroos et al. | 2019 | Player value | Performance value for recruitment | [KDD](https://doi.org/10.1145/3292500.3330758) |
| PlayeRank: data-driven performance evaluation and player ranking | Pappalardo et al. | 2019 | Player ranking | Role-aware scouting metric | [ACM TIST](https://doi.org/10.1145/3343172) |
| Player Vectors: Characterizing Soccer Players' Playing Style | Decroos, Davis | 2020 | Player similarity | Find stylistically similar / replacement players | [ECML PKDD](https://doi.org/10.1007/978-3-030-46133-1_34) |
| Artificial neural networks and player recruitment | Barron et al. | 2018 | Recruitment ML | Predicting suitability / level | [PLoS ONE](https://doi.org/10.1371/journal.pone.0205818) |
| Ranking soccer teams on the basis of their current strength | Ley et al. | 2017 | League strength | Quantify the "step-up" / adaptation across leagues | [arXiv](https://arxiv.org/abs/1705.09575) |
| Quantifying relative soccer league strength (applied) | ElHabr | 2021 | League adjustment | Hands-on cross-league strength | [blog](https://tonyelhabr.rbind.io/posts/soccer-league-strength/) |
| Opta Power Rankings — strongest leagues (applied) | The Analyst | — | League quality | Industry league-strength reference | [The Analyst](https://theanalyst.com/articles/strongest-football-leagues-in-the-world-opta-power-rankings) |
| Mythbusting Set-Pieces in Soccer | Power, Hobbs, Ruiz, Wei, Lucey | 2018 | Mythbusting methodology | The set-piece "mythbusting" paper that inspired this project's recruitment-mythbusting framing | [Stats Perform / Sloan](https://www.statsperform.com/resource/exploiting-inefficiencies-at-set-pieces-sloan/) |
| Relative age effect in elite soccer: more early-born players, but no better valued | PLoS ONE | 2018 | Recruitment bias | A selection bias that doesn't translate to value — a "myth" to test | [PLoS ONE](https://doi.org/10.1371/journal.pone.0192209) |
| A framework of cognitive biases that might influence talent identification in sport | Int. Rev. Sport & Ex. Psych. | 2025 | Bias framing | Catalogues cognitive biases in talent ID — helps frame the questions | [IRSEP](https://doi.org/10.1080/1750984X.2025.2556393) |
| Racial bias in football commentary: the pace & power effect (study) | RunRepeat | 2020 | Evaluation bias (applied) | Attribute-description bias relevant to scouting language | [RunRepeat](https://runrepeat.com/racial-bias-study-soccer) |
| Valuing on-the-ball actions in soccer: a critical comparison of xT and VAEP | Van Roy, Robberechts, Decroos, Davis | 2020 | Action-valuation methods | Starting point if pivoting to *improving* the valuation model | [PDF](https://tomdecroos.github.io/reports/xt_vs_vaep.pdf) |
| _add as you read_ | | | | | |

> **Two framings for an open-ended brief:** (a) **recruitment mythbusting** —
> test industry assumptions (adaptation tax, contract length, window timing) in
> the spirit of *Mythbusting Set-Pieces*, using the bias literature above to frame
> hypotheses; or (b) a **methods pivot** — if the domain framing proves hard,
> focus on *improving an action-valuation model* (VAEP / xT / EPV / SoccerMap) as
> the recruitment signal. Both are legitimate routes.

### Project 7 — Pitch Control & Expected Threat Modelling

The core literature for spatial control + value layers (xT / EPV), plus the
open-data tutorials the student can build on **before** club data access lands.

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Wide Open Spaces: measuring space creation in professional soccer | Fernández & Bornn | 2018 | Pitch control model | Foundational pitch-control / space-occupation surface from tracking | [MIT Sloan PDF](https://www.lukebornn.com/papers/fernandez_sloan_2018.pdf) |
| Beyond Expected Goals | Spearman | 2018 | Off-ball scoring opportunity via pitch control | Builds a scoring-opportunity value on top of pitch control | [MIT Sloan](https://www.sloansportsconference.com/research-papers/beyond-expected-goals) |
| Physics-Based Modeling of Pass Probabilities in Soccer | Spearman, Basye, Dick, Hotovy, Pop | 2017 | Pass / control probability | The pass-probability model under most pitch-control implementations | [MIT Sloan](https://www.sloansportsconference.com/research-papers/physics-based-modeling-of-pass-probabilities-in-soccer) |
| A framework for the fine-grained evaluation of the instantaneous expected value of soccer possessions (EPV) | Fernández, Bornn & Cervone | 2021 | Expected Possession Value | The EPV layer to put on top of pitch control | [Machine Learning (Springer)](https://link.springer.com/article/10.1007/s10994-021-05989-6) |
| Introducing Expected Threat (xT) | Singh (Karun) | 2019 | Expected Threat grid | Accessible xT formulation; good baseline value layer from event data | [karun.in blog](https://karun.in/blog/expected-threat.html) |
| Friends of Tracking — pitch control tutorials & code | Shaw (Laurie) et al. | 2020 | Pitch control from tracking (hands-on) | Tutorial videos + `LaurieOnTracking` code; ideal starting point | [YouTube](https://www.youtube.com/c/FriendsofTracking) · [GitHub](https://github.com/Friends-of-Tracking-Data-FoTD/LaurieOnTracking) |
| Metrica Sports sample tracking data | Metrica Sports | 2020 | Open tracking dataset | Free tracking data to prototype on; frame shape ≈ our SecondSpectrum data | [GitHub](https://github.com/metrica-sports/sample-data) |
| SoccerMap: a deep-learning architecture for visually-interpretable analysis | Fernández, Bornn | 2021 | Pass/value surfaces | CNN full-pitch probability/value surfaces from tracking | [arXiv](https://arxiv.org/abs/2010.10202) |
| Actions Speak Louder than Goals (VAEP) | Decroos et al. | 2019 | Possession value | Event-based value to compare with spatial value | [KDD](https://doi.org/10.1145/3292500.3330758) |
| Player Vectors: Characterizing Soccer Players' Playing Style | Decroos, Davis | 2020 | Style / representation | Complements spatial value with style | [ECML PKDD](https://doi.org/10.1007/978-3-030-46133-1_34) |
| socceraction (xT implementation) | ML-KULeuven | — | Tooling | Ready-made xT/VAEP to build the value layer | [GitHub](https://github.com/ML-KULeuven/socceraction) |
| Unlocking the potential of big data (tactical review) | Goes et al. | 2021 | Spatial/tracking review | Context for tracking-based value models | [EJSS](https://doi.org/10.1080/17461391.2020.1747552) |
| _add as you read_ | | | | | |

> **Tip for the spatial-control student:** the SecondSpectrum frame format
> (per-player `xyz` + `speed`, ball position, 25 fps) maps closely onto the
> Metrica / Friends-of-Tracking public data. Build and validate the pitch-control
> + xT pipeline on public tracking first, then repoint it at `nffc_data.ssio`
> once you have your access key.

### Project 8 — Automated Set-Piece Clustering

| Title | Authors | Year | Topic | Notes | Link |
|---|---|---|---|---|---|
| Routine Inspection: A Playbook for Corner Kicks | Shaw, Gopaladesikan | 2020 | Corner-routine clustering | The key reference — clusters attacking corner routines from tracking | [Springer (MLSA)](https://doi.org/10.1007/978-3-030-64912-8_1) |
| Individual role classification for players defending corners in football (soccer) | Bauer, Anzer, Smith | 2022 | Defensive role detection | CNN+LSTM infers man/zonal + 7 defensive roles from positional data | [JQAS](https://doi.org/10.1515/jqas-2022-0003) |
| Mythbusting Set-Pieces in Soccer | Power, Hobbs, Ruiz, Wei, Lucey | 2018 | Set-piece structure detection | Image-based detection of set-piece structure; directly on-topic | [Stats Perform / Sloan](https://www.statsperform.com/resource/exploiting-inefficiencies-at-set-pieces-sloan/) |
| Automatic Discovery of Tactics in Spatio-Temporal Soccer Match Data | Decroos, Van Haaren, Davis | 2018 | Pattern clustering | Method transferable to set-piece routines | [KDD](https://doi.org/10.1145/3219819.3219832) |
| Technical–tactical analysis of corner kicks in male soccer (systematic review) | Applied Sciences | 2025 | Set-piece review | Domain grounding on corner tactics | [MDPI](https://doi.org/10.3390/app15094984) |
| Understanding the variability and determinants of corner-kick effectiveness | (Science & Medicine in Football) | 2025 | Set-piece effectiveness | What makes corners work | [ScienceDirect](https://www.sciencedirect.com/science/article/pii/S3050544525000337) |
| Using Dynamic Time Warping to Find Patterns in Time Series | Berndt, Clifford | 1994 | DTW method | Clustering player-run trajectories during routines | [AAAI WS PDF](https://cdn.aaai.org/Workshops/1994/WS-94-03/WS94-03-031.pdf) |
| SoccerMap (spatial surfaces from tracking) | Fernández, Bornn | 2021 | Tracking methods | Tracking representation useful for set-piece modelling | [arXiv](https://arxiv.org/abs/2010.10202) |
| Player Vectors: characterizing playing style (NMF) | Decroos, Davis | 2020 | NMF representation | Spatial decomposition transferable to routine representation | [ECML PKDD](https://doi.org/10.1007/978-3-030-46133-1_34) |
| SoccerMix: representing soccer actions with mixture models | Decroos, Van Roy, Davis | 2020 | Soft clustering | Mixture-model clustering transferable to set-piece actions | [ECML PKDD](https://doi.org/10.1007/978-3-030-67670-4_28) |
| Effective and efficient sports play retrieval (play2vec) | Wang, Long, Cong, Ju | 2019 | Deep sequence embedding | Embeds tracking play sequences — directly applicable to corner routines | [KDD](https://doi.org/10.1145/3292500.3330927) |
| Neural Discrete Representation Learning (VQ-VAE) | van den Oord et al. | 2017 | Discrete deep methods | Learn a discrete "vocabulary" of routines — novel angle | [arXiv](https://arxiv.org/abs/1711.00937) |
| kloppy (tracking ingestion, supports SecondSpectrum) | PySport | — | Tooling | Load/standardise the tracking needed for corners | [kloppy.pysport.org](https://kloppy.pysport.org/) |
| Pass-clustering model (applied, code) | Kolliari (jakeyk11) | — | Applied clustering | A worked clustering pipeline to adapt | [GitHub](https://github.com/jakeyk11/football-data-analytics) |
| _add as you read_ | | | | | |

> **Note:** the general clustering/representation methods above (NMF, mixture
> models, deep sequence embeddings, discrete-latent models) plus DTW and the
> tactic-discovery reference make set-piece routine clustering largely a
> clustering-of-trajectories problem — the same toolkit as Project 4.
