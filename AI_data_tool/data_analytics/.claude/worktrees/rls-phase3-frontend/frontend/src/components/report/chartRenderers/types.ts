import type { CalcColumnFormat } from '../../../services/api'

export interface ChartRendererProps {
  rows: any[]
  data: any
  cfg: any
  rtl: boolean
  broadcasts: boolean
  localSelected: unknown
  onClickPoint: (v: unknown) => void
  measureFmt?: CalcColumnFormat
  measure2Fmt?: CalcColumnFormat
  allFormats?: Record<string, CalcColumnFormat | undefined>
}
