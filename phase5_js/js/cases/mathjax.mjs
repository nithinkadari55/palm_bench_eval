// 100 TeX formulas (base, ams, newcommand, color, boldsymbol, cancel, braket, mathtools,
// mhchem) and 20 MathML formulas.
const TEX = String.raw`
x^2 + y^2 = z^2
\frac{a}{b} + \frac{c}{d} = \frac{ad + bc}{bd}
\sqrt{2} \approx 1.41421
\sqrt[3]{x^3 + y^3}
e^{i\pi} + 1 = 0
\int_0^\infty e^{-x^2}\,dx = \frac{\sqrt{\pi}}{2}
\sum_{k=1}^{n} k = \frac{n(n+1)}{2}
\prod_{p\ \text{prime}} \frac{1}{1 - p^{-s}} = \zeta(s)
\lim_{x \to 0} \frac{\sin x}{x} = 1
\binom{n}{k} = \frac{n!}{k!\,(n-k)!}
\begin{pmatrix} a & b \\ c & d \end{pmatrix}^{-1} = \frac{1}{ad-bc}\begin{pmatrix} d & -b \\ -c & a \end{pmatrix}
\begin{bmatrix} 1 & 0 & 0 \\ 0 & 1 & 0 \\ 0 & 0 & 1 \end{bmatrix}
\det\begin{vmatrix} a & b \\ c & d \end{vmatrix} = ad - bc
\begin{cases} x^2 & x \ge 0 \\ -x & x < 0 \end{cases}
\begin{aligned} f(x) &= (x+1)^2 \\ &= x^2 + 2x + 1 \end{aligned}
\begin{align} a &= b + c \\ d &= e + f \end{align}
\begin{gather} x = 1 \\ y = 2 \end{gather}
\begin{equation} E = mc^2 \label{eq:emc} \end{equation}
\nabla \cdot \mathbf{E} = \frac{\rho}{\varepsilon_0}
\nabla \times \mathbf{B} - \frac{1}{c^2}\frac{\partial \mathbf{E}}{\partial t} = \mu_0 \mathbf{J}
\oint_{\partial \Sigma} \mathbf{E} \cdot d\boldsymbol{\ell} = -\frac{d}{dt}\iint_\Sigma \mathbf{B} \cdot d\mathbf{S}
\hat{H}\psi = i\hbar\frac{\partial}{\partial t}\psi
\langle \psi | \phi \rangle
\bra{\psi} A \ket{\phi}
\Set{x \in \mathbb{R} | x > 0}
\mathbb{N} \subset \mathbb{Z} \subset \mathbb{Q} \subset \mathbb{R} \subset \mathbb{C}
\mathcal{L}\{f\}(s) = \int_0^\infty f(t) e^{-st}\,dt
\mathfrak{g} = \mathfrak{sl}_2(\mathbb{C})
\mathscr{F}(\omega) = \int_{-\infty}^{\infty} f(t)e^{-i\omega t}\,dt
\mathrm{d}x \wedge \mathrm{d}y
\boldsymbol{\alpha} + \boldsymbol{\beta}
\alpha\beta\gamma\delta\epsilon\zeta\eta\theta\iota\kappa\lambda\mu\nu\xi\pi\rho\sigma\tau\upsilon\phi\chi\psi\omega
\Gamma\Delta\Theta\Lambda\Xi\Pi\Sigma\Upsilon\Phi\Psi\Omega
\aleph_0 < 2^{\aleph_0}
\forall \epsilon > 0\ \exists \delta > 0 : |x - a| < \delta \implies |f(x) - f(a)| < \epsilon
A \cup B,\ A \cap B,\ A \setminus B,\ A \triangle B
\neg (p \land q) \iff \neg p \lor \neg q
f: X \to Y,\quad x \mapsto f(x)
a \equiv b \pmod{n}
\gcd(a, b) \cdot \operatorname{lcm}(a, b) = ab
\overline{z} = a - bi
\underline{\text{important}}
\overbrace{a + b + c}^{\text{three}}
\underbrace{1 + 1 + \cdots + 1}_{n\ \text{times}}
\vec{v} = v_x\hat{\imath} + v_y\hat{\jmath}
\dot{x},\ \ddot{x},\ \tilde{x},\ \bar{x},\ \acute{x},\ \grave{x},\ \breve{x},\ \check{x}
\widehat{ABC} \quad \widetilde{xyz}
\left( \frac{a}{b} \right) \left[ \frac{c}{d} \right] \left\{ \frac{e}{f} \right\}
\left\langle x, y \right\rangle
\left. \frac{df}{dx} \right|_{x=0}
\Bigg( \bigg( \Big( \big( x \big) \Big) \bigg) \Bigg)
\lfloor x \rfloor + \lceil y \rceil
\|x\|_2 = \sqrt{\sum_i x_i^2}
\xrightarrow[\text{below}]{\text{above}}
A \xleftarrow{f} B
\leftarrow \rightarrow \leftrightarrow \Leftarrow \Rightarrow \Leftrightarrow \uparrow \downarrow
\hookrightarrow \twoheadrightarrow \rightsquigarrow \longmapsto
\le \ge \ne \approx \sim \simeq \cong \equiv \propto \ll \gg
\lesssim \gtrsim \leqslant \geqslant \nleq \ngeq \precsim \succsim
\in \notin \ni \subseteq \supseteq \subsetneq \supsetneq
\infty \partial \nabla \emptyset \varnothing \top \bot \angle \measuredangle
\int \iint \iiint \oint \idotsint
\sum\nolimits_{i} \prod\limits_{j}
\textstyle\sum_{n=1}^\infty \frac{1}{n^2} = \frac{\pi^2}{6}
\displaystyle\frac{1}{1 + \frac{1}{1 + \frac{1}{1 + x}}}
\cfrac{1}{1 + \cfrac{1}{1 + \cfrac{1}{1 + \cdots}}}
x_{i_1}^{j_2} + {}_{a}^{b}X_{c}^{d}
\sideset{_a^b}{_c^d}\sum
\overset{\text{def}}{=} \quad \underset{n \to \infty}{\longrightarrow}
\stackrel{?}{=}
\mathrm{Tr}(AB) = \mathrm{Tr}(BA)
\color{red}{x} + \color{blue}{y} = \color{green}{z}
\colorbox{yellow}{$a+b$}
\textcolor{#cc6600}{\text{orange text}}
\cancel{x} + \bcancel{y} + \xcancel{z}
\cancelto{0}{x}
\newcommand{\RR}{\mathbb{R}} f: \RR^n \to \RR
\def\abs#1{\left|#1\right|} \abs{x - y}
\coloneqq \quad \eqqcolon
\begin{dcases} \frac{1}{x} & x > 0 \\ 0 & \text{otherwise} \end{dcases}
\begin{pmatrix*}[r] -1 & 3 \\ 2 & -4 \end{pmatrix*}
\prescript{14}{6}{\mathrm{C}}
\ce{H2O}
\ce{2H2 + O2 -> 2H2O}
\ce{CO2 + C -> 2CO}
\ce{Hg^2+ ->[I-] HgI2 ->[I-] [Hg^{II}I4]^2-}
\ce{A <=> B}
\pu{123 kJ/mol}
\begin{array}{c|cc} & 0 & 1 \\ \hline 0 & 0 & 0 \\ 1 & 0 & 1 \end{array}
\begin{matrix} a & b \\ c & d \end{matrix} \quad \begin{smallmatrix} a & b \\ c & d \end{smallmatrix}
\begin{CD} A @>f>> B \\ @VgVV @VVhV \\ C @>>k> D \end{CD}
\boxed{E = h\nu}
\text{The area is } \pi r^2 \text{ square units.}
\frac{\partial^2 u}{\partial t^2} = c^2 \nabla^2 u
P(A \mid B) = \frac{P(B \mid A)\,P(A)}{P(B)}
\mathbb{E}[X] = \sum_x x\,p(x),\quad \operatorname{Var}(X) = \mathbb{E}[X^2] - \mathbb{E}[X]^2
f(x) = \frac{1}{\sigma\sqrt{2\pi}} e^{-\frac{1}{2}\left(\frac{x-\mu}{\sigma}\right)^2}
\hbar\omega\left(n + \tfrac{1}{2}\right)
R_{\mu\nu} - \tfrac{1}{2}R\,g_{\mu\nu} + \Lambda g_{\mu\nu} = \frac{8\pi G}{c^4}T_{\mu\nu}
\undefinedmacro{x} + 1
`.trim().split('\n');

const MML = [
  '<math><mi>x</mi><mo>=</mo><mfrac><mrow><mo>-</mo><mi>b</mi><mo>&#xB1;</mo><msqrt><msup><mi>b</mi><mn>2</mn></msup><mo>-</mo><mn>4</mn><mi>a</mi><mi>c</mi></msqrt></mrow><mrow><mn>2</mn><mi>a</mi></mrow></mfrac></math>',
  '<math><msup><mi>e</mi><mrow><mi>i</mi><mi>&#x3C0;</mi></mrow></msup><mo>+</mo><mn>1</mn><mo>=</mo><mn>0</mn></math>',
  '<math display="block"><munderover><mo>&#x2211;</mo><mrow><mi>k</mi><mo>=</mo><mn>1</mn></mrow><mi>n</mi></munderover><msup><mi>k</mi><mn>2</mn></msup></math>',
  '<math><mroot><mi>x</mi><mn>3</mn></mroot></math>',
  '<math><mrow><mo>(</mo><mtable><mtr><mtd><mn>1</mn></mtd><mtd><mn>2</mn></mtd></mtr><mtr><mtd><mn>3</mn></mtd><mtd><mn>4</mn></mtd></mtr></mtable><mo>)</mo></mrow></math>',
  '<math><msubsup><mo>&#x222B;</mo><mn>0</mn><mn>1</mn></msubsup><msup><mi>x</mi><mn>2</mn></msup><mi>d</mi><mi>x</mi></math>',
  '<math><mover><mi>x</mi><mo>&#x2192;</mo></mover><mo>&#x22C5;</mo><mover><mi>y</mi><mo>&#x2192;</mo></mover></math>',
  '<math><munder><mi>lim</mi><mrow><mi>n</mi><mo>&#x2192;</mo><mi>&#x221E;</mi></mrow></munder><msup><mrow><mo>(</mo><mn>1</mn><mo>+</mo><mfrac><mn>1</mn><mi>n</mi></mfrac><mo>)</mo></mrow><mi>n</mi></msup></math>',
  '<math><mi mathvariant="double-struck">R</mi><mo>&#x2286;</mo><mi mathvariant="double-struck">C</mi></math>',
  '<math><mi mathvariant="fraktur">g</mi><mo>,</mo><mi mathvariant="script">L</mi><mo>,</mo><mi mathvariant="bold">v</mi></math>',
  '<math><mtext>if&#xA0;</mtext><mi>x</mi><mo>&gt;</mo><mn>0</mn></math>',
  '<math><menclose notation="box"><mi>E</mi><mo>=</mo><mi>m</mi><msup><mi>c</mi><mn>2</mn></msup></menclose></math>',
  '<math><mpadded width="+2em"><mi>a</mi></mpadded><mspace width="1em"/><mi>b</mi></math>',
  '<math><mstyle mathcolor="red"><mi>x</mi></mstyle><mo>+</mo><mstyle mathbackground="yellow"><mi>y</mi></mstyle></math>',
  '<math><mmultiscripts><mi>X</mi><mi>c</mi><mi>d</mi><mprescripts/><mi>a</mi><mi>b</mi></mmultiscripts></math>',
  '<math><mfrac linethickness="0"><mi>n</mi><mi>k</mi></mfrac></math>',
  '<math><mrow><mo stretchy="true">{</mo><mfrac><mi>a</mi><mi>b</mi></mfrac><mo stretchy="true">}</mo></mrow></math>',
  '<math><mi>f</mi><mo>&#x2061;</mo><mo>(</mo><mi>x</mi><mo>)</mo><mo>=</mo><mrow><mo>{</mo><mtable columnalign="left"><mtr><mtd><mn>1</mn></mtd><mtd><mi>x</mi><mo>&#x2265;</mo><mn>0</mn></mtd></mtr><mtr><mtd><mn>0</mn></mtd><mtd><mtext>otherwise</mtext></mtd></mtr></mtable></mrow></math>',
  '<math><semantics><mrow><mi>a</mi><mo>+</mo><mi>b</mi></mrow><annotation encoding="application/x-tex">a+b</annotation></semantics></math>',
  '<math><merror><mtext>deliberate error element</mtext></merror></math>'
];

export default [
  ...TEX.map((src, i) => ({ id: 'tex-' + String(i + 1).padStart(3, '0'), input: { kind: 'tex', src, display: true } })),
  ...MML.map((src, i) => ({ id: 'mml-' + String(i + 1).padStart(2, '0'), input: { kind: 'mathml', src, display: true } }))
];

export const counts = { tex: TEX.length, mathml: MML.length };
