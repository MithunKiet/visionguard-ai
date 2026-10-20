import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import { Link } from "react-router-dom";
import type { DetectionHealthData } from "../hooks/useDetectionHealth";

export function DetectionHealthNotice({ data }: { data?: DetectionHealthData }) {
  if (!data) return <Alert severity="warning" action={<Button component={Link} to="/detection-health">Check health</Button>}>
    Detection health is unavailable. Zero recorded violations does not confirm safety.
  </Alert>;
  const s = data.summary;
  return <Alert severity={s.gap_cameras ? "warning" : "info"} action={<Button component={Link} to="/detection-health">View cameras</Button>}>
    {s.expected_cameras === 0 ? "No cameras are currently expected to monitor. Check camera setup."
      : s.gap_cameras ? `${s.gap_cameras} of ${s.expected_cameras} expected cameras lack recent detection. Zero recorded violations does not confirm safety.`
      : `Recent detection confirmed on ${s.detecting_cameras} of ${s.expected_cameras} expected cameras.`}
    {s.paused_cameras > 0 && ` ${s.paused_cameras} paused or maintenance cameras excluded.`}
  </Alert>;
}
