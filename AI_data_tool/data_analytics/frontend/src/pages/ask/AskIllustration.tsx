import AskRobot from './AskRobot'
import { useRobotMood } from './robotMood'

/**
 * The Ask AI hero picture (step 10): the robot on its stage, in the state the
 * page reports (robotMood.ts). `small` is the dataset-picked hero: the robot
 * alone, smaller.
 */
export default function AskIllustration({ small = false }: { small?: boolean }) {
  const { state, nod } = useRobotMood()
  return <AskRobot state={state} nod={nod} bare={small} />
}
