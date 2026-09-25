import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import StatisticsPanel from './StatisticsPanel'
import { analysisCatalogueApi } from '../services/api'
import type { DatasetColumn } from '../services/api'

/**
 * One screen for every runnable analysis, driven by the registry.
 *
 * It began as eight statistical tests that shipped with working endpoints and
 * NO frontend entry point — half the registry was reachable only by the agent,
 * which can mention an analysis but not invoke one. It stayed at eight because
 * the panel filtered on `result_kind === 'statistical_test'` and posted to a
 * hand-written name→slug map, so anything that did not return a `TestResult`
 * was invisible here however finished it was.
 *
 * Now the catalogue says which analyses are `runnable` and one endpoint runs
 * any of them, so the tests are about the generic machinery: that the picker
 * comes from the REGISTRY, that the form is built from each spec's schema
 * (including fields that are NOT column names), and that a result kind this
 * screen has never seen still renders something a reader can use.
 */

vi.mock('../services/api', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  analysisCatalogueApi: { registry: vi.fn(), run: vi.fn() },
}))

const col = (name: string): DatasetColumn =>
  ({ id: 0, name, dtype: 'numeric', missing_pct: 0, stats: {} } as DatasetColumn)
const COLUMNS = [col('revenue'), col('region'), col('units'), col('cost')]

const column = (extra: Record<string, unknown> = {}) =>
  ({ type: 'string', format: 'column', ...extra })

const SPECS = [
  {
    name: 'compare_groups',
    description: 'Is a measure genuinely different across groups?',
    result_kind: 'statistical_test', runnable: true,
    params_schema: {
      type: 'object',
      required: ['value_col', 'group_col'],
      properties: {
        value_col: column({ description: 'The numeric measure to compare.' }),
        group_col: column({ description: 'The categorical column.' }),
      },
    },
  },
  {
    name: 'regression',
    description: 'How much does each predictor move the target?',
    result_kind: 'statistical_test', runnable: true,
    params_schema: {
      type: 'object',
      required: ['target', 'predictors'],
      properties: {
        target: column(),
        predictors: { type: 'array', format: 'column', items: { type: 'string' } },
      },
    },
  },
  {
    name: 'correlation_test',
    description: 'Do two measures move together?',
    result_kind: 'statistical_test', runnable: true,
    params_schema: {
      type: 'object',
      required: ['col_a', 'col_b'],
      properties: {
        col_a: column(), col_b: column(),
        method: { type: 'string', enum: ['pearson', 'spearman'] },
      },
    },
  },
  {
    name: 'goal_seek',
    description: 'Work backwards from a target.',
    result_kind: 'goal_seek', runnable: true,
    params_schema: {
      type: 'object',
      required: ['x_column', 'y_column', 'target_y'],
      properties: {
        x_column: column(), y_column: column(),
        target_y: { type: 'number', description: 'The value of y you want to reach.' },
        x_min: { type: ['number', 'null'] },
      },
    },
  },
  {
    name: 'explain_response',
    description: 'Which columns move a chosen response?',
    result_kind: 'explanation', runnable: true,
    params_schema: {
      type: 'object', required: ['response'],
      properties: { response: column() },
    },
  },
  // Filtered out: listed in the catalogue, but with no handler behind it, so
  // choosing it could only ever produce a 400.
  {
    name: 'forecast_ets', description: 'Project a series forward.',
    result_kind: 'forecast', runnable: false,
    params_schema: { type: 'object', properties: {} },
  },
]

const TEST_RESULT = {
  kind: 'compare_groups', statistic: 3.2, p_value: 0.0001,
  effect_size: 0.62, effect_name: 'cohens_d', effect_label: 'medium' as const,
  significant: true, alpha: 0.05, n: 900,
  detail: { test: "Welch's t-test" },
  interpretation: 'Statistically significant difference, with a medium effect.',
  caveats: ["Welch's t-test is used, which does not assume equal variances"],
}

const envelope = (kind: string, result: unknown, name = 'compare_groups') =>
  ({ analysis: name, result_kind: kind, params: {}, result })

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(analysisCatalogueApi.registry).mockResolvedValue(SPECS as never)
  vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
    envelope('statistical_test', TEST_RESULT) as never)
})

const panel = () => render(<StatisticsPanel datasetId={1} columns={COLUMNS} />)
const picker = () => screen.findByLabelText(/^analysis$/i)

describe('the picker comes from the registry', () => {
  it('offers every runnable analysis', async () => {
    panel()
    const values = Array.from((await picker() as HTMLSelectElement).options).map(o => o.value)
    expect(values).toContain('compare_groups')
    expect(values).toContain('regression')
    expect(values).toContain('goal_seek')
    expect(values).toContain('explain_response')
  })

  it('leaves out an analysis the catalogue lists but cannot run', async () => {
    // It is real and documented, but has no handler, so offering it would only
    // ever produce a 400 the user cannot act on.
    panel()
    const values = Array.from((await picker() as HTMLSelectElement).options).map(o => o.value)
    expect(values).not.toContain('forecast_ets')
  })

  it('shows the registry’s own description as help text', async () => {
    // Written as the question a user would ask, so it is used verbatim.
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    expect(await screen.findByText(/genuinely different across groups/i)).toBeInTheDocument()
  })

  it('reports a failure to load the catalogue instead of an empty picker', async () => {
    vi.mocked(analysisCatalogueApi.registry).mockRejectedValue(new Error('down'))
    panel()
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load/i)
  })
})

describe('the form is built from the schema', () => {
  it('renders a column select per column-valued string field', async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    expect(await screen.findByLabelText(/^value col/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^group col/i)).toBeInTheDocument()
  })

  it('renders a multi-select for an array of columns', async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'regression' } })
    expect(await screen.findByLabelText('predictors units')).toBeInTheDocument()
  })

  it('renders a plain select for an enum field', async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'correlation_test' } })
    const method = await screen.findByLabelText(/^method/i) as HTMLSelectElement
    expect(Array.from(method.options).map(o => o.value)).toEqual(['pearson', 'spearman'])
  })

  it('renders a number input where a number is wanted, not a column list', async () => {
    /**
     * The defect this pins. Every property that was not an enum or an array
     * became a dropdown of the dataset's columns — fine while every analysis
     * took nothing but column names. `goal_seek.target_y` is the value the
     * user wants to REACH: rendered as a column picker there was no way to
     * type a number into it, and the analysis could not be run at all.
     */
    panel()
    fireEvent.change(await picker(), { target: { value: 'goal_seek' } })
    const field = await screen.findByLabelText(/^target y/i) as HTMLInputElement
    expect(field.tagName).toBe('INPUT')
    expect(field.type).toBe('number')
  })

  it('treats a nullable number as a number too', async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'goal_seek' } })
    expect((await screen.findByLabelText(/^x min/i) as HTMLInputElement).type).toBe('number')
  })

  it('will not run until every required field is chosen', async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    const run = await screen.findByRole('button', { name: /run/i })
    expect(run).toBeDisabled()

    fireEvent.change(screen.getByLabelText(/^value col/i), { target: { value: 'revenue' } })
    expect(run).toBeDisabled()          // one of two
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    await waitFor(() => expect(run).toBeEnabled())
  })

  it('counts a typed zero as an answered required field', async () => {
    // `!!0` is false. A required target of zero is a perfectly ordinary goal,
    // and a truthiness check would leave Run disabled with the field filled in.
    panel()
    fireEvent.change(await picker(), { target: { value: 'goal_seek' } })
    fireEvent.change(await screen.findByLabelText(/^x column/i), { target: { value: 'cost' } })
    fireEvent.change(screen.getByLabelText(/^y column/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^target y/i), { target: { value: '0' } })
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run/i })).toBeEnabled())
  })

  it('clears parameters when the analysis changes', async () => {
    // Carrying `predictors` into a test with no such field would post a
    // parameter the endpoint rejects.
    panel()
    const p = await picker()
    fireEvent.change(p, { target: { value: 'regression' } })
    fireEvent.click(await screen.findByLabelText('predictors units'))
    fireEvent.change(p, { target: { value: 'compare_groups' } })
    fireEvent.change(p, { target: { value: 'regression' } })

    expect((await screen.findByLabelText('predictors units') as HTMLInputElement).checked)
      .toBe(false)
  })
})

describe('running an analysis', () => {
  const runCompareGroups = async () => {
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('posts the chosen parameters to the chosen analysis', async () => {
    await runCompareGroups()
    await waitFor(() => expect(analysisCatalogueApi.run).toHaveBeenCalledWith(
      1, 'compare_groups', { value_col: 'revenue', group_col: 'region' }))
  })

  it('sends a number as a number, not as its text', async () => {
    // The endpoint's schema types `target_y` as a number; posting "500" makes
    // the request depend on the server coercing a string.
    panel()
    fireEvent.change(await picker(), { target: { value: 'goal_seek' } })
    fireEvent.change(await screen.findByLabelText(/^x column/i), { target: { value: 'cost' } })
    fireEvent.change(screen.getByLabelText(/^y column/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^target y/i), { target: { value: '500' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
    await waitFor(() => expect(analysisCatalogueApi.run).toHaveBeenCalledWith(
      1, 'goal_seek', { x_column: 'cost', y_column: 'revenue', target_y: 500 }))
  })

  it('omits an optional field the user left blank', async () => {
    // Posting `x_min: ""` would fail the number schema; posting nothing is
    // what "optional" means.
    panel()
    fireEvent.change(await picker(), { target: { value: 'goal_seek' } })
    fireEvent.change(await screen.findByLabelText(/^x column/i), { target: { value: 'cost' } })
    fireEvent.change(screen.getByLabelText(/^y column/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^target y/i), { target: { value: '500' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
    await waitFor(() => expect(analysisCatalogueApi.run).toHaveBeenCalled())
    const [, , params] = vi.mocked(analysisCatalogueApi.run).mock.calls[0]
    expect(params).not.toHaveProperty('x_min')
  })

  it('shows the effect size beside the p-value', async () => {
    // THE property. At two million rows a p-value alone is nearly content-free,
    // so a card leading with the asterisk would manufacture confident trivia.
    await runCompareGroups()
    expect(await screen.findByText(/cohens d/i)).toBeInTheDocument()
    // The label sits beside the number, not in the prose -- "medium" also
    // appears in the interpretation sentence, so match the stat block.
    expect(screen.getByText(/· medium/)).toBeInTheDocument()
    expect(screen.getByText('0.62')).toBeInTheDocument()
    expect(screen.getByText('p-value')).toBeInTheDocument()
  })

  it('shows the caveats, which are part of the answer', async () => {
    await runCompareGroups()
    expect(await screen.findByText(/does not assume equal variances/i)).toBeInTheDocument()
  })

  it('surfaces the backend’s own refusal rather than a generic message', async () => {
    // "Only 3 event(s); Cox needs about 10 per predictor" tells the user what
    // to change; "something went wrong" does not.
    vi.mocked(analysisCatalogueApi.run).mockRejectedValue(
      { response: { data: { detail: 'Only 3 event(s); Cox regression needs about 10' } } })
    await runCompareGroups()
    expect(await screen.findByText(/needs about 10/i)).toBeInTheDocument()
  })
})

describe('a result kind picks its own view', () => {
  const runAndSee = async (name: string, kind: string, result: unknown,
                           fill: () => void) => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      envelope(kind, result, name) as never)
    panel()
    fireEvent.change(await picker(), { target: { value: name } })
    await screen.findByRole('button', { name: /run/i })
    fill()
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('draws the importance bars for an explanation', async () => {
    // The same bars `ExplainDialog` draws — one component, so the two screens
    // cannot drift into showing the same numbers two different ways.
    await runAndSee('explain_response', 'explanation', {
      response: 'revenue', note: null, relationship: null,
      factors: [{ column: 'units', kind: 'numeric', score: 0.9, relative: 1 },
                { column: 'region', kind: 'category', score: 0.4, relative: 0.44 }],
    }, () => fireEvent.change(screen.getByLabelText(/^response/i),
                              { target: { value: 'revenue' } }))
    expect(await screen.findByTestId('bar-units')).toBeInTheDocument()
    expect(screen.getByTestId('bar-region')).toBeInTheDocument()
  })

  it('answers a goal seek in a sentence, with its extrapolation warning', async () => {
    await runAndSee('goal_seek', 'goal_seek', {
      required_x: 812, slope: 2, intercept: 1, r2: 0.94,
      x_observed_min: 0, x_observed_max: 130, within_observed_range: false,
    }, () => {
      fireEvent.change(screen.getByLabelText(/^x column/i), { target: { value: 'cost' } })
      fireEvent.change(screen.getByLabelText(/^y column/i), { target: { value: 'revenue' } })
      fireEvent.change(screen.getByLabelText(/^target y/i), { target: { value: '1625' } })
    })
    // Through `toLocaleString`, so the expectation goes through it too: under
    // an Arabic locale the panel renders ٨١٢, which is correct for a reader
    // there and would make a hardcoded "812" a false failure.
    expect(await screen.findByTestId('goal-result'))
      .toHaveTextContent((812).toLocaleString())
    expect(screen.getByText(/extrapolation/i)).toBeInTheDocument()
  })

  it('names the factor and the outcome in the goal-seek answer', async () => {
    // "would need to be ≈ 812" is unreadable without knowing what would.
    await runAndSee('goal_seek', 'goal_seek', {
      required_x: 812, r2: 0.94, within_observed_range: true,
    }, () => {
      fireEvent.change(screen.getByLabelText(/^x column/i), { target: { value: 'cost' } })
      fireEvent.change(screen.getByLabelText(/^y column/i), { target: { value: 'revenue' } })
      fireEvent.change(screen.getByLabelText(/^target y/i), { target: { value: '1625' } })
    })
    expect(await screen.findByTestId('goal-result')).toHaveTextContent(/cost/)
  })

  it('renders a kind it has never seen rather than nothing at all', async () => {
    /**
     * The whole point of a catalogue-driven screen is that a new analysis
     * appears without frontend work. If an unrecognised `result_kind` rendered
     * blank, every new analysis would still need a code change here — and the
     * failure would be silent: a Run that succeeds and shows nothing.
     */
    await runAndSee('compare_groups', 'something_new', {
      clusters: 4, silhouette: 0.61,
      rows: [{ label: 'a', size: 10 }, { label: 'b', size: 12 }],
    }, () => {
      fireEvent.change(screen.getByLabelText(/^value col/i), { target: { value: 'revenue' } })
      fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    })
    expect(await screen.findByText('silhouette')).toBeInTheDocument()
    expect(screen.getByText('0.61')).toBeInTheDocument()
    // An array of objects is a table, not "[object Object]".
    expect(screen.getByRole('table')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
  })
})

describe('the fallback shows an answer, not an inventory', () => {
  /**
   * Photographed live against `segment`, whose envelope carries a filled
   * `columns` list, a filled `meta`, an EMPTY `rows`, and a `kind` that repeats
   * the heading. Rendered naively that is two headings over nothing and one
   * word printed twice — noise in exactly the place a reader is trying to find
   * the number.
   */
  const runGeneric = async (result: unknown) => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      { analysis: 'segment', result_kind: 'segment', params: {}, result } as never)
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('omits a heading for an empty list', async () => {
    await runGeneric({ kind: 'segment', rows: [], columns: [{ name: 'revenue' }] })
    await screen.findByRole('table')
    expect(screen.queryByText('rows')).not.toBeInTheDocument()
  })

  it('omits a heading for an empty object', async () => {
    await runGeneric({ kind: 'segment', warnings: [], meta: {}, columns: [{ name: 'x' }] })
    await screen.findByRole('table')
    expect(screen.queryByText('meta')).not.toBeInTheDocument()
  })

  it('does not print the kind twice', async () => {
    await runGeneric({ kind: 'segment', columns: [{ name: 'x' }] })
    await screen.findByRole('table')
    expect(screen.getAllByText('segment')).toHaveLength(1)
  })

  it('still shows a kind that differs from the heading', async () => {
    // Only the exact restatement is dropped: `detail.kind` naming a different
    // thing is real information.
    await runGeneric({ kind: 'kmeans', columns: [{ name: 'x' }] })
    await screen.findByRole('table')
    expect(screen.getByText('kmeans')).toBeInTheDocument()
  })
})

describe('a decision tree', () => {
  /**
   * The one analysis here that answers "why" with something a person reads out
   * loud: *margin_pct <= 11.9 → three quarters churn*. Pretty-printed JSON of a
   * nested tree is technically the same information and useless as an answer,
   * so this kind gets a view: the branches as an indented list, each with how
   * many rows took it.
   */
  const TREE = {
    kind: 'decision_tree', task: 'classification', target: 'churned',
    predictors_used: ['margin_pct', 'region'],
    predictors_skipped: [{ column: 'invoice_id', reason: '400 distinct values' }],
    score: 0.91, score_name: 'accuracy', train_score: 0.94,
    n_train: 300, n_test: 100, max_depth: 4,
    importance: [{ column: 'margin_pct', importance: 0.87 },
                 { column: 'region', importance: 0.13 }],
    caveats: ['That is association, not causation.'],
    tree: {
      feature: 'margin_pct', label: 'margin_pct <= 11.94', threshold: 11.94,
      samples: 300, prediction: 'no', confidence: 0.72, children: [
        { feature: null, label: null, samples: 90, prediction: 'yes',
          confidence: 0.94, children: [] },
        { feature: null, label: null, samples: 210, prediction: 'no',
          confidence: 0.98, children: [] },
      ],
    },
  }

  const showTree = async () => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      envelope('decision_tree', TREE, 'decision_tree') as never)
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('draws the tree as a structure, not as pretty-printed JSON', async () => {
    /**
     * The assertion that matters, and the one four earlier versions of these
     * tests missed: `margin_pct <= 11.94` appears inside a JSON blob too, so
     * matching on the text alone passes against exactly the rendering this
     * view exists to replace.
     */
    await showTree()
    const nodes = await screen.findAllByTestId('tree-node')
    expect(nodes.length).toBe(3)          // one split, two leaves
    expect(document.querySelector('pre')).toBeNull()
  })

  it('reads the split as a sentence', async () => {
    await showTree()
    const [root] = await screen.findAllByTestId('tree-node')
    expect(root).toHaveTextContent('margin_pct <= 11.94')
  })

  it('says how many rows took each branch', async () => {
    // Row counts go through `toLocaleString`, so the expectation does too:
    // under an Arabic locale 210 renders ٢١٠, right for that reader and a
    // false failure against a hardcoded string.
    await showTree()
    const nodes = await screen.findAllByTestId('tree-node')
    expect(nodes[1]).toHaveTextContent((90).toLocaleString())
    expect(nodes[2]).toHaveTextContent((210).toLocaleString())
  })

  it('states what each leaf predicts, with its confidence', async () => {
    await showTree()
    const nodes = await screen.findAllByTestId('tree-node')
    expect(nodes[1]).toHaveTextContent(/yes/)
    expect(nodes[1]).toHaveTextContent(/94/)
  })

  it('shows the held-out score beside the training one', async () => {
    // A tree scored on its own training rows reports nothing. Both numbers, so
    // the gap between them is visible.
    await showTree()
    const scores = await screen.findByTestId('tree-score')
    expect(scores).toHaveTextContent('0.91')
    expect(scores).toHaveTextContent('0.94')
  })

  it('names the columns it could not use', async () => {
    // Absence from the importance list otherwise reads as "considered and
    // unimportant", which is the opposite of the truth.
    await showTree()
    await screen.findByText(/margin_pct <= 11\.94/)
    expect(screen.getByText(/invoice_id/)).toBeInTheDocument()
  })

  it('keeps the caveats', async () => {
    await showTree()
    expect(await screen.findByText(/not causation/i)).toBeInTheDocument()
  })
})

describe('automated prediction', () => {
  /**
   * Several models on one split, and the question that decides whether the
   * winner means anything: did it beat simply guessing? The generic fallback
   * would render the champion as a JSON blob and bury the baseline among the
   * scalars — which is exactly the presentation that lets an 82% accuracy look
   * impressive next to a 79% coin flip.
   */
  const result = (over: Record<string, unknown> = {}) => ({
    kind: 'automated_prediction', task: 'classification', target: 'churned',
    score_name: 'accuracy',
    candidates: [
      { model: 'random forest', score: 0.94, train_score: 0.99, n_test: 125, is_baseline: false, error: null },
      { model: 'decision tree', score: 0.91, train_score: 0.92, n_test: 125, is_baseline: false, error: null },
      { model: 'always the most common', score: 0.62, train_score: 0.61, n_test: 125, is_baseline: true, error: null },
    ],
    champion: { model: 'random forest', score: 0.94, train_score: 0.99, n_test: 125, is_baseline: false, error: null },
    baseline_score: 0.62, lift_over_baseline: 0.32, beats_baseline: true,
    predictors_used: ['margin_pct'], predictors_skipped: [],
    n_train: 375, n_test: 125,
    caveats: ['The winning model is not saved.'],
    ...over,
  })

  const show = async (over: Record<string, unknown> = {}) => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      envelope('automated_prediction', result(over), 'automated_prediction') as never)
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('leads with the winner', async () => {
    await show()
    expect(await screen.findByTestId('prediction-champion'))
      .toHaveTextContent(/random forest/)
  })

  it('states the verdict against guessing, in words', async () => {
    await show()
    const verdict = await screen.findByTestId('prediction-verdict')
    expect(verdict).toHaveTextContent(/0\.62/)          // what guessing scores
    expect(verdict).toHaveTextContent(/better/i)
  })

  it('says so plainly when the winner did NOT earn it', async () => {
    // The answer that matters most and is least often given.
    await show({ beats_baseline: false, lift_over_baseline: 0.01,
                 baseline_score: 0.93,
                 champion: { model: 'decision tree', score: 0.94, train_score: 0.99,
                             n_test: 125, is_baseline: false, error: null } })
    expect(await screen.findByTestId('prediction-verdict'))
      .toHaveTextContent(/no better|not.*better|barely/i)
  })

  it('lists every candidate it tried, baseline included', async () => {
    await show()
    await screen.findByTestId('prediction-champion')
    const rows = screen.getAllByTestId('prediction-candidate')
    expect(rows).toHaveLength(3)
    expect(rows[2]).toHaveTextContent(/always the most common/)
  })

  it('marks which one is the baseline', async () => {
    await show()
    await screen.findByTestId('prediction-champion')
    expect(screen.getAllByTestId('prediction-candidate')[2])
      .toHaveTextContent(/guess|baseline/i)
  })

  it('keeps the caveats', async () => {
    await show()
    expect(await screen.findByText(/not saved/i)).toBeInTheDocument()
  })
})

describe('text topics', () => {
  /**
   * A topic is a cluster of words and the comments behind it. Rendered as JSON
   * it is unreadable; rendered as words alone it invites the reader to trust a
   * label the model never assigned. So: the terms, the count, and a real
   * comment — the quote is what lets someone judge whether the cluster means
   * what its words suggest.
   */
  const TOPICS = {
    kind: 'text_topics', column: 'comment',
    documents_used: 200, documents_skipped: 4, vocabulary: 107,
    topics: [
      { rank: 1, documents: 74,
        terms: [{ term: 'onboarding', weight: 1.2 }, { term: 'confused', weight: 0.9 }],
        examples: ['Onboarding left several of us confused.'] },
      { rank: 2, documents: 68,
        terms: [{ term: 'filters', weight: 1.1 }, { term: 'saved', weight: 0.8 }],
        examples: ['The new filters saved us hours every week.'] },
    ],
    caveats: ['A topic is a cluster of words the model found together, not a name.'],
  }

  const show = async () => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      envelope('text_topics', TOPICS, 'text_topics') as never)
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('shows each topic as its terms', async () => {
    await show()
    const topics = await screen.findAllByTestId('topic')
    expect(topics).toHaveLength(2)
    expect(topics[0]).toHaveTextContent('onboarding')
    expect(topics[0]).toHaveTextContent('confused')
  })

  it('says how many comments fell into each', async () => {
    await show()
    const topics = await screen.findAllByTestId('topic')
    expect(topics[0]).toHaveTextContent((74).toLocaleString())
  })

  it('quotes a real comment for each', async () => {
    // The words alone are hard to judge; the comment behind them is not.
    await show()
    expect(await screen.findByText(/Onboarding left several of us confused/))
      .toBeInTheDocument()
  })

  it('does not present the terms as a name', async () => {
    // The caveat is load-bearing: a topic list reads like a taxonomy unless
    // something says it is not one.
    await show()
    expect(await screen.findByText(/not a name/i)).toBeInTheDocument()
  })

  it('reports how much text it worked from', async () => {
    await show()
    const summary = await screen.findByTestId('topics-summary')
    expect(summary).toHaveTextContent((200).toLocaleString())
  })
})

describe('a what-if scenario', () => {
  /**
   * The difference between the two projections is the number somebody takes to
   * a meeting, so it leads. But a scenario built on a factor with p = 0.48 is a
   * guess wearing a number, and the p-value has to sit beside the factor rather
   * than in a footnote — seen on real data, where +10% units produced a
   * confident-looking -19,309 from a coefficient with no evidence behind it.
   */
  const SCENARIO = (over: Record<string, unknown> = {}) => ({
    kind: 'forecast_scenario', measure: 'revenue',
    factors: [
      { column: 'cost', coefficient: 1.133, p_value: 0.0000,
        observed_min: 267344, observed_max: 416231, recent_level: 390000 },
      { column: 'units', coefficient: -1.957, p_value: 0.4783,
        observed_min: 15061, observed_max: 21970, recent_level: 19000 },
    ],
    adjustments: { units: 0.1 },
    baseline: [{ name: '2026-01', value: 387000 }],
    scenario: [{ name: '2026-01', value: 383800 }],
    baseline_total: 2325509, scenario_total: 2306200, difference: -19309,
    r2: 0.879, periods_fitted: 24, horizon: 6, extrapolating: false,
    caveats: ['This is association, not intervention.'],
    ...over,
  })

  const show = async (over: Record<string, unknown> = {}) => {
    vi.mocked(analysisCatalogueApi.run).mockResolvedValue(
      envelope('forecast_scenario', SCENARIO(over), 'forecast_scenario') as never)
    panel()
    fireEvent.change(await picker(), { target: { value: 'compare_groups' } })
    fireEvent.change(await screen.findByLabelText(/^value col/i), { target: { value: 'revenue' } })
    fireEvent.change(screen.getByLabelText(/^group col/i), { target: { value: 'region' } })
    fireEvent.click(screen.getByRole('button', { name: /run/i }))
  }

  it('leads with the difference the scenario makes', async () => {
    await show()
    expect(await screen.findByTestId('scenario-difference'))
      .toHaveTextContent((-19309).toLocaleString())
  })

  it('shows each factor with the evidence behind it', async () => {
    await show()
    const rows = await screen.findAllByTestId('scenario-factor')
    expect(rows).toHaveLength(2)
    expect(rows[1]).toHaveTextContent('units')
    expect(rows[1]).toHaveTextContent('0.478')
  })

  it('marks a factor with no evidence behind it', async () => {
    // p = 0.48 must not look like p = 0.0001 at a glance.
    await show()
    const rows = await screen.findAllByTestId('scenario-factor')
    expect(rows[1]).toHaveTextContent(/no evidence|weak|not significant/i)
    expect(rows[0]).not.toHaveTextContent(/no evidence|weak|not significant/i)
  })

  it('warns when the scenario leaves the observed range', async () => {
    await show({ extrapolating: true })
    expect(await screen.findByTestId('scenario-extrapolation'))
      .toHaveTextContent(/outside|never/i)
  })

  it('does not warn when it stays inside it', async () => {
    await show()
    await screen.findByTestId('scenario-difference')
    expect(screen.queryByTestId('scenario-extrapolation')).not.toBeInTheDocument()
  })

  it('keeps the association caveat', async () => {
    await show()
    expect(await screen.findByText(/not intervention/i)).toBeInTheDocument()
  })
})

/**
 * Analyses need the whole frame, which a live dataset does not hand over.
 *
 * Photographed on the running app: the Analysis tab on "Demo — Live Orders
 * (DirectQuery)" offered "— choose —" as though any of them would run. They are
 * import-mode work — they read every row — so the author picks one, fills in its
 * parameters, and is refused at the end.
 *
 * The same shape as the Models tab next door, and the same fix: say it before
 * the form, not after the button.
 */
describe('on a DirectQuery dataset', () => {
  /* The refusal above was never true of the backend -- `/analysis/run` has
     handled DirectQuery since it shipped. It was true of the FRAME that path
     produced: `run_direct_query(widget_type="table")` returns a preview, and
     the analyses were being answered from 50 rows while the UI presented the
     result as the dataset's. So the guard was hiding a defect, not a limit.

     With the frame fixed (up to `analysis_row_cap`, provenance attached) the
     analyses are offered, and the panel accounts for what was measured instead
     of refusing. */
  it('offers the analyses, and says the source is read live', async () => {
    render(<StatisticsPanel datasetId={1} columns={[]} mode="directquery" />)
    expect(await screen.findByLabelText(/analysis/i)).toBeInTheDocument()
    expect(screen.getByTestId('directquery-analysis-notice')).toBeInTheDocument()
  })

  it('does not claim exactness it cannot promise', async () => {
    /* The sentence has to leave room for a sample: a figure drawn from part of
       the data must never be presented as though it came from all of it. */
    render(<StatisticsPanel datasetId={1} columns={[]} mode="directquery" />)
    const notice = await screen.findByTestId('directquery-analysis-notice')
    expect(notice.textContent).toMatch(/how many rows it measured/i)
    expect(notice.textContent).not.toMatch(/import-mode datasets only/i)
  })

  it('shows no such notice on an imported dataset', async () => {
    render(<StatisticsPanel datasetId={1} columns={[]} mode="import" />)
    await screen.findByLabelText(/analysis/i)
    expect(screen.queryByTestId('directquery-analysis-notice')).toBeNull()
  })

  it('offers them as usual on an imported dataset', async () => {
    render(<StatisticsPanel datasetId={1} columns={[]} mode="import" />)
    expect(await screen.findByLabelText(/analysis/i)).toBeInTheDocument()
  })
})
