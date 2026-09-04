# Introduction

Autoregressive (AR) transformers remain the dominant paradigm for large
language models, a position earned through scale and mature training
infrastructure rather than an inherent advantage of sequential decoding
. AR models generate text token by token and achieve remarkable
performance across a wide range of tasks, but they possess intrinsic
limitations: left-to-right decoding restricts parallelization during
inference , precise structural control (e.g., length or format
constraints) is difficult to enforce during sampling, and dynamic,
task-aware perception requires costly chain-of-thought or multi-round
processing .

Diffusion models—originally developed for continuous domains such as
image generation —offer a compelling alternative. By framing generation
as an iterative denoising process, diffusion models enable parallel
token generation, bidirectional context modeling, and fine-grained
controllability . The application of diffusion to language has
progressed from small-scale experiments to commercial-scale deployments
, with commercial deployments reporting roughly an order-of-magnitude
latency reduction over speed-optimized AR baselines under batch decoding
.

This literature review synthesizes the current state of diffusion models
for LLMs, organized as follows: Section 2 covers the mathematical and
conceptual foundations. Section 3 traces the evolution from continuous
to discrete formulations. Section 4 categorizes representative models
and techniques. Section 5 examines applications and empirical results.
Section 6 discusses challenges and open problems. Section 7 outlines
future directions.

# Foundations of Diffusion Models

## The Diffusion Framework

Diffusion models are generative models that learn to reverse a gradual
noising process . The framework consists of two core processes:

**Forward Process (Noising):** Starting from clean data
$`\mathbf{x}_0`$, a Markov chain gradually adds noise over $`T`$
timesteps, producing increasingly corrupted versions
$`\mathbf{x}_1, \mathbf{x}_2, \ldots, \mathbf{x}_T`$ until the data
approximates pure noise .

**Reverse Process (Denoising):** A neural network is trained to invert
this process, learning to predict and remove noise step by step,
ultimately generating new samples from random noise .

Three foundational works shaped the continuous diffusion framework. The
Denoising Diffusion Probabilistic Model (DDPM) established the core
variational framework: training reduces to a simple weighted
mean-squared-error objective on noise prediction, which made large-scale
training practical for the first time . Denoising Diffusion Implicit
Models (DDIM) generalized sampling to non-Markovian trajectories,
enabling deterministic sampling with orders-of-magnitude fewer steps and
thus making iterative refinement computationally viable at inference
time . Score-based generative modeling through stochastic differential
equations (SDEs) then unified DDPM and score matching under a
continuous-time formulation, providing the theoretical lens through
which modern samplers—including the discrete formulations discussed
below—are analyzed . For discrete state spaces, the analogous
continuous-time object is a continuous-time Markov chain (CTMC):
Campbell et al. derived a continuous-time evidence lower bound for
discrete denoising models with tau-leaping and predictor-corrector
samplers , and Sun et al. developed the corresponding score-based
continuous-time formulation . These CTMC frameworks underpin the
continuous-time objectives of modern masked diffusion LLMs.

## The Challenge of Discrete Data

A fundamental challenge arises when applying diffusion to language: text
is inherently discrete (composed of tokens), whereas diffusion models
were originally designed for continuous data (e.g., image pixels) . In
continuous domains, Gaussian noise can be naturally added and removed;
in discrete domains, adding noise to a token renders it invalid .

This challenge has led to two distinct approaches :

1.  **Continuous Diffusion in Embedding Space:** Mapping discrete tokens
    to continuous embeddings and applying standard diffusion in this
    space .

2.  **Discrete Diffusion over Tokens:** Defining noise processes
    directly over discrete token spaces using transition matrices .

To handle discrete data directly, Austin et al. proposed Structured
Denoising Diffusion Models in Discrete State-Spaces (D3PM), which
generalizes the forward process to a family of discrete transition
matrices—including uniform and absorbing-state (masking) kernels .
Concurrently, Hoogeboom et al. introduced multinomial diffusion with
argmax flows for categorical data, an earlier and closely related
formulation .

# Evolution of Diffusion Language Models

The evolution of diffusion models for language can be traced through
several distinct phases .

## Early Foundations (2015-2020)

The thermodynamic origins of diffusion models were established through
DDPM and DDIM , which introduced the core principles of Markovian
noising and denoising on continuous data, later unified in continuous
time by the score-SDE formulation . These foundational works
demonstrated that iterative refinement from noise could produce
high-quality samples, though they were initially applied exclusively to
continuous domains like images.

## First Text-Specific Adaptations (2021-2022)

The first systematic efforts to adapt diffusion for text emerged in this
period. Zou et al. provided the first systematic survey of diffusion for
non-autoregressive text generation, defining both discrete (mask-based)
and continuous (Gaussian embedding) formulations .

Key pioneering works include:

**D3PM** (Austin et al., 2021): This work proposed a diffusion-like
generative model for discrete data, defining a family of discrete damage
processes that generalize the diffusion framework beyond Gaussian noise
. It demonstrated that absorbing-state discrete diffusion can produce
coherent categorical samples without timestep inputs , establishing the
technical foundation on which most modern dLLMs rest.

**Diffusion-LM** (Li et al., 2022): This work developed a
non-autoregressive language model based on continuous diffusions,
embedding Gaussian noise into token representations . Diffusion-LM
demonstrated successful control for six challenging fine-grained control
tasks—including syntactic structure, length, and lexical
constraints—significantly outperforming prior plug-in methods in
controllable text generation .

**DiffusionBERT** (Wang et al., 2022): This work presented a generative
masked language model based on discrete diffusion models, leveraging
BERT as its backbone . By recognizing that diffusion models and
pre-trained language models share a denoising objective, DiffusionBERT
achieved significant improvements over existing diffusion models for
text .

**SSD-LM** (Han et al., 2022): This work introduced a
semi-autoregressive diffusion-based language model that iteratively
generates blocks of text, allowing for flexible output length while
enabling local bidirectional context updates within each block . Its
block-wise design is architecturally significant: rather than treating
parallelism and sequential structure as mutually exclusive, SSD-LM shows
they can be combined. The work also demonstrated that with simplex
projection, the diffusion process can be conducted directly in the
natural vocabulary space .

**CDCD** (Dieleman et al., 2022): This framework modeled categorical
data with diffusion processes that are continuous both in time and input
space , demonstrating efficacy on several language modeling tasks and
providing score interpolation techniques for improved likelihood
estimation .

## The Shift to Discrete Diffusion (2023-2024)

Continuous approaches faced a persistent difficulty: mapping continuous
embeddings back to discrete tokens without quality degradation, since
small perturbations in embedding space can decode to unrelated tokens.
Recent analyses suggest this gap was driven at least as much by
unexamined design choices in early continuous systems as by any
fundamental property of discreteness , but empirically research shifted
decisively toward discrete formulations during this period .

**Masked Diffusion Language Models (MDLM)** (Sahoo et al., 2024): This
work introduced a masked discrete diffusion model featuring a novel
substitution-based parameterization that simplifies the absorbing-state
diffusion loss to a Rao–Blackwellized mixture of classical masked
language modeling cross-entropies . MDLM demonstrated that masked
diffusion could close much of the perplexity gap to AR models at small
scales .

**SEDD** (Lou et al., 2023): Rather than parameterizing a
vocabulary-sized transition matrix, SEDD estimates the ratios of the
data distribution across noise scales with a score-entropy objective .
This ratio-based view is the direct ancestor of the score
parameterizations used in subsequent scaled masked diffusion models, and
SEDD showed competitive likelihoods against GPT-2 at its scale .

**GIDD** (von Rütte et al., 2025): Generalized interpolating discrete
diffusion unifies masked and uniform noising in a single forward-process
family, including hybrid schedules with self-correction capability . In
the reported small-model studies, mask-only models generally performed
better on likelihood and downstream tasks; whether uniform components
help token-constrained scaling remains an open hypothesis .

## Industrial-Scale Diffusion LLMs (2025-Present)

The most recent phase has witnessed the scaling of diffusion language
models to commercial scale, with performance rivaling or matching
autoregressive counterparts .

**Mercury** (Inception Labs, 2025): The first commercially available
diffusion-based LLM, Mercury achieves throughputs of 1,109 tokens/sec
(Mini) and 737 tokens/sec (Small) on NVIDIA H100 GPUs—up to $`10\times`$
faster than speed-optimized frontier models—while maintaining comparable
quality on coding benchmarks . Mercury Coder Mini achieves an 88% score
on HumanEval and ranks second on Copilot Arena with just 25ms latency .

**LLaDA** (Nie et al., 2025): The first diffusion-based language model
to achieve performance comparable to autoregressive models at the 8B
scale, trained entirely from scratch with fully bidirectional attention
. LLaDA2.0 later scaled to 100B parameters, representing the first
diffusion model at this scale . Complementary scaling work adapted
existing AR checkpoints to the diffusion objective: DiffuLLaMA reached
7B by adaptation , and the masked-diffusion MDM study reported a loss
scaling rate similar to AR models while quantifying a roughly
$`16\times`$ compute gap at matched validation loss . Earlier
likelihood-based diffusion approaches faced a substantially larger
($`\sim`$<!-- -->64$`\times`$) matched-likelihood disadvantage , so
these gaps reflect different objectives and estimators rather than a
single constant penalty. Compute-optimal training studies further find
diffusion-specific tradeoffs, including higher optimal data budgets than
AR models in single-epoch regimes .

## Diffusion-Native Post-Training (2025-Present)

Adapting preference optimization and reinforcement learning to diffusion
decoders has become its own research thread. SEPO applies policy
gradients to discrete diffusion with self-normalized importance sampling
and clipped ratios ; d1 adapts GRPO to masked dLLMs through one-step
unmasking with verifiable rewards ; VRPO reduces the variance of
ELBO-based DPO estimators through Monte Carlo allocation and antithetic
sampling, yielding LLaDA 1.5 ; and coupled-GRPO uses complementary mask
noise for paired completions in code models such as DiffuCoder .
Reported gains are promising but rest on limited data, task, and model
coverage.

# Categorization of Diffusion Language Models

## By Diffusion Space

**Continuous-Space Models:** These models map discrete tokens to
continuous embeddings and apply standard Gaussian diffusion . Examples
include Diffusion-LM , SSD-LM , and CDCD . While these models benefit
from the well-understood mathematics of continuous diffusion, they face
challenges in maintaining semantic consistency when projecting back to
discrete tokens .

**Discrete-Space Models:** These models operate directly on token spaces
using discrete noise processes such as absorbing-state (masking) or
uniform transitions . Examples include D3PM , MDLM , DiffusionBERT ,
Mercury , and LLaDA . Discrete models have largely superseded continuous
approaches in recent work .

## By Generation Strategy

**Fully Parallel Models:** These models generate all tokens
simultaneously through iterative refinement. Examples include MDLM and
LLaDA .

**Semi-Autoregressive Models:** These models generate blocks of text
iteratively, combining the parallelism of diffusion with the sequential
structure of autoregression. SSD-LM exemplifies this approach .

## By Architecture

**Transformer-Based:** Most diffusion language models employ Transformer
architectures, as the choice of architecture is orthogonal to the
diffusion paradigm . Mercury, LLaDA, and DiffusionBERT all use
Transformer backbones.

**Hybrid Architectures:** Some works explore combining diffusion with
other paradigms, such as integrating LLMs with diffusion models for
multimodal generation .

# Applications and Empirical Results

## Code Generation

Coding represents a particularly latency-sensitive domain where
diffusion models have demonstrated exceptional value . Mercury Coder
achieves:

- **HumanEval:** 88% (Mini) and 90% (Small) pass@1

- **MultiPL-E:** Competitive performance across C++, Java, JavaScript,
  PHP, Bash, and TypeScript

- **Fill-in-the-Middle:** State-of-the-art performance of 93.1% (Small)
  on single-line FIM

- **Speed:** 1,109 tokens/sec (Mini) and 737 tokens/sec (Small) on H100
  GPUs

These results demonstrate that diffusion models can match or exceed AR
models in code generation while achieving order-of-magnitude speed
improvements. The throughput figures should be read in context: they are
aggregate batch throughputs on H100 GPUs, and independent analyses
attribute part of the speedup to the reduced number of denoising steps
(Mercury uses a 10-step schedule) rather than to parallel decoding alone
.

## Controllable Text Generation

One of the earliest and most compelling applications of diffusion to
language was controllable generation. Diffusion-LM demonstrated
successful control across six fine-grained tasks, significantly
outperforming prior work . The bidirectional nature of diffusion enables
constraints to be applied throughout the generation process rather than
only left-to-right .

## Multimodal Generation

The integration of LLMs and diffusion models has emerged as a key
research frontier for advancing multimodal generation, reasoning, and
cross-domain understanding . This integration enables:

- **Text-to-Image Synthesis:** Leveraging LLMs for semantic
  understanding and diffusion models for high-quality generation

- **Text-to-Video Synthesis:** Extending diffusion to temporal domains
  with LLM guidance

- **Unified Multimodal Models:** Combining understanding and generation
  capabilities in a single framework

## Human Evaluation

Mercury Coder Mini, evaluated on Copilot Arena, ranks tied for second
place in code completion quality, surpassing speed-optimized models like
GPT-4o Mini and Gemini-1.5-Flash, and even larger models like GPT-4o .
With an average latency of just 25ms, it is approximately $`4\times`$
faster than GPT-4o Mini, which averages around 100ms in the same
evaluation .

# Challenges (Open Problems) vs. Future Directions

Because the remaining two analytical sections address related but
distinct concerns, we state their partition explicitly: this section
catalogs *unsolved problems with evidence*, while Section 7 outlines
*proposed research programs*. Each challenge below maps to one or more
directions that follow.

## Challenges and Open Problems

## Inference Efficiency

While diffusion models offer theoretical parallelism, practical
efficiency depends on the number of denoising steps. Early diffusion
models required hundreds of steps; training-free acceleration techniques
such as KV caching and parallel decoding (Fast-dLLM), as well as learned
step-distillation samplers, have since reduced this to 10-20 steps with
minimal quality loss . The trade-off between generation quality and
inference speed remains an active area of research .

## Long-Sequence Handling

Diffusion models face challenges in handling long sequences due to the
computational cost of processing entire sequences in each denoising step
. Context windows currently range from 32K (Mercury) to 128K with
positional-extension techniques such as RoPE scaling, compared to 1M+
for some AR models.

## Scaling Laws

The scaling properties of diffusion language models are less well
understood than those of autoregressive models . While larger diffusion
models consistently outperform smaller ones, the relationship between
model size, data, and performance requires further investigation .

## Alignment and Fine-Tuning

Adapting diffusion models to follow instructions through RLHF or DPO
presents unique challenges, as the denoising objective differs
fundamentally from the autoregressive next-token prediction loss .
Techniques developed for AR models may not transfer directly.

## Evaluation Protocols

Standardized benchmarks and evaluation protocols for diffusion language
models remain underdeveloped . Many existing benchmarks were designed
for AR models and may not capture the unique strengths and weaknesses of
diffusion-based generation .

# Future Directions

## Unified Autoregressive-Diffusion Models

Recent work has explored unifying AR and diffusion paradigms through
hyperschedules and hybrid architectures . Such unification could enable
models to leverage the strengths of both approaches: the deep reasoning
of AR and the speed and controllability of diffusion. This direction
directly addresses the scaling-law and alignment challenges of Section
6, since hybrid schedules can retain AR-style likelihood training while
inheriting diffusion-style parallel decoding.

## Efficient Inference Techniques

Advances in caching mechanisms , adaptive correction sampling , and
decoding parallelism promise to further reduce inference latency. The
development of specialized hardware and inference engines for diffusion
models represents another important direction .

## Scaling to Frontier Performance

While diffusion models have demonstrated comparable performance to
speed-optimized AR models, matching frontier models (e.g., GPT-4o,
Claude 3.5 Sonnet) on complex reasoning benchmarks remains an open
challenge . Scaling diffusion models to hundreds of billions of
parameters, as demonstrated by LLaDA2.0 , may help close this gap.

## Agentic Applications

The speed advantages of diffusion models make them particularly
attractive for agentic workloads requiring multiple reasoning and
execution cycles . However, memory and context limitations must be
addressed for complex, multi-step agentic tasks.

## Multimodal Unification

The integration of diffusion models and LLMs for unified multimodal
understanding and generation represents a promising frontier . Such
unified models could serve as the foundation for next-generation AI
systems capable of seamless interaction across modalities.

# Conclusion

Diffusion models for large language models have evolved from small-scale
experiments to commercial-scale deployments in just a few years. The
shift from continuous to discrete formulations—driven by the
token-projection difficulties of embedding-space approaches, though
recent evidence suggests the gap was narrower than commonly assumed
—coupled with advances in training and inference efficiency, has enabled
diffusion-based LLMs to achieve performance comparable to autoregressive
models while delivering order-of-magnitude speed improvements under
batch decoding .

Key milestones include the pioneering Diffusion-LM , the discrete
diffusion frameworks of D3PM and MDLM , the industrial-scale deployment
of Mercury , and the 100B-scale LLaDA2.0 . These developments position
diffusion models as a compelling alternative—and complement—to the
dominant autoregressive paradigm .

However, significant challenges remain, including inference efficiency
optimization, long-sequence handling, scaling law characterization,
alignment techniques, and standardized evaluation protocols . Addressing
these challenges will be essential for realizing the full potential of
diffusion-based language models in real-world applications.

The future of language modeling likely lies not in a single paradigm but
in hybrid approaches that leverage the complementary strengths of
autoregressive and diffusion models —combining the deep reasoning of AR
with the speed, parallelism, and controllability of diffusion.

<div class="thebibliography">

99

J. Ho, A. Jain, and P. Abbeel, “Denoising diffusion probabilistic
models,” *Advances in Neural Information Processing Systems*, vol. 33,
pp. 6840–6851, 2020.

X. L. Li, J. Thickstun, I. Gulrajani, P. Liang, and T. B. Hashimoto,
“Diffusion-LM improves controllable text generation,” *arXiv preprint
arXiv:2205.14217*, 2022.

C.-Y. Tseng, D. Zhang, Z. Bi, and J. Song, “Diffusion-based large
language models survey,” *TechRxiv*, 2025.

R. Yu, Q. Li, and X. Wang, “Discrete diffusion in large language and
multimodal models: A survey,” *arXiv preprint arXiv:2506.13759*, 2025.

T. Li, M. Chen, B. Guo, and Z. Shen, “A survey on diffusion language
models,” *arXiv preprint arXiv:2508.10875*, 2025.

A. Benjdira and A. M. Ali, “Integrating large language models and
diffusion models in generative AI tasks: Progress, challenges, and
future directions,” *TechRxiv*, 2025.

H. Zou, Z. M. Kim, and D. Kang, “A survey of diffusion models in natural
language processing,” *arXiv preprint arXiv:2305.14671*, 2023.

S. Sahoo et al., “Simple and effective masked diffusion language
models,” *NeurIPS*, 2024.

K. Wang et al., “DiffusionBERT: Improving generative masked language
models with diffusion models,” *ACL*, 2023.

X. Han et al., “SSD-LM: Semi-autoregressive simplex-based diffusion
language model for text generation and modular control,” *ACL*, 2023.

S. Dieleman et al., “Continuous diffusion for categorical data,” *arXiv
preprint*, 2022.

Y. Nie et al., “Large language diffusion models (LLaDA),” *NeurIPS*,
2025.

S. Khanna et al., “Mercury: Ultra-fast language models based on
diffusion,” *Inception Labs Technical Report*, 2025.

J. Song, C. Meng, and S. Ermon, “Denoising diffusion implicit models,”
*arXiv preprint arXiv:2010.02502*, 2021.

J. Austin, D. D. Johnson, J. Ho, D. Tarlow, and R. van den Berg,
“Structured denoising diffusion models in discrete state-spaces,” *arXiv
preprint arXiv:2107.03006*, 2021.

Y. Song, J. Sohl-Dickstein, D. P. Kingma, A. Kumar, S. Ermon, and B.
Poole, “Score-based generative modeling through stochastic differential
equations,” *arXiv preprint arXiv:2011.13456*, 2021.

E. Hoogeboom, D. Nielsen, P. Jaini, P. Forré, and M. Welling, “Argmax
flows and multinomial diffusion: Learning categorical distributions,”
*arXiv preprint arXiv:2102.05379*, 2021.

J. Shen, J. Zhao, Z. He, and Z. Lin, “CoDAR: Continuous diffusion
language models are more powerful than you think,” *arXiv preprint
arXiv:2603.02547*, 2026.

Z. Jin, B. Wang, X. Lin, L. Bing, and A. Sun, “On the role of
discreteness in diffusion LLMs,” *arXiv preprint arXiv:2512.22630*,
2025.

X. Wang, C. Xu, Y. Jin, J. Jin, H. Zhang, and Z. Deng, “Diffusion LLMs
can do faster-than-AR inference via discrete diffusion forcing,” *arXiv
preprint arXiv:2508.09192*, 2025.

Y. Fu, L. Whalen, Z. Ye, X. Dong, S. Diao, and J. Liu, “Efficient-DLM:
From autoregressive to diffusion language models, and beyond in speed,”
*arXiv preprint arXiv:2512.14067*, 2025.

C. Wu, H. Zhang, and S. Xue, “Fast-dLLM: Training-free acceleration of
diffusion LLM by enabling KV cache and parallel decoding,” *arXiv
preprint arXiv:2505.22618*, 2025.

A. Campbell, J. Benton, V. De Bortoli, T. Rainforth, G. Deligiannidis,
and A. Doucet, “A continuous time framework for discrete denoising
models,” *arXiv preprint arXiv:2205.14987*, 2022.

H. Sun, L. Yu, B. Dai, D. Schuurmans, and H. Dai, “Score-based
continuous-time discrete diffusion models,” *arXiv preprint
arXiv:2211.16750*, 2022.

A. Lou, C. Meng, and S. Ermon, “Discrete diffusion modeling by
estimating the ratios of the data distribution,” *arXiv preprint
arXiv:2310.16834*, 2023.

D. von Rütte, J. Fluri, Y. Ding, A. Orvieto, B. Schölkopf, and T.
Hofmann, “Generalized interpolating discrete diffusion,” *arXiv preprint
arXiv:2503.04482*, 2025.

I. Gulrajani and T. B. Hashimoto, “Likelihood-based diffusion language
models,” *arXiv preprint arXiv:2305.18619*, 2023.

S. Nie, F. Zhu, Z. Gao, D. Du, T. Pang, Q. Liu, C. Li, and M. Lin,
“Scaling up masked diffusion models on text,” *arXiv preprint
arXiv:2410.18514*, 2024.

S. Gong, S. Agarwal, Y. Zhang, J. Ye, L. Zheng, M. Li, C. An, P. Zhao,
and T. Pfister, “Scaling diffusion language models via adaptation from
autoregressive models,” *arXiv preprint arXiv:2410.17891*, 2024.

J. Ni, Q. Liu, C. Du, L. Dou, H. Yan, Z. Wang, and W. Lu, “Training
optimal large diffusion language models,” *arXiv preprint
arXiv:2510.03280*, 2025.

O. Zekri and N. Boullé, “Fine-tuning discrete diffusion models with
policy gradient methods,” *arXiv preprint arXiv:2502.01384*, 2025.

S. Zhao, D. Gupta, Q. Zheng, and A. Grover, “d1: Scaling reasoning in
diffusion large language models via reinforcement learning,” *arXiv
preprint arXiv:2504.12216*, 2025.

F. Zhu, R. Wang, S. Nie, X. Zhang, C. Wu, J. Chen, Y. Liu, and M. Lin,
“LLaDA 1.5: Variance-reduced preference optimization for large language
diffusion models,” *arXiv preprint arXiv:2505.19223*, 2025.

S. Gong, R. Zhang, H. Zheng, J. Gu, N. Jaitly, L. Kong, and Y. Li,
“DiffuCoder: Understanding and improving masked diffusion models for
code generation,” *arXiv preprint arXiv:2506.20639*, 2025.

</div>
