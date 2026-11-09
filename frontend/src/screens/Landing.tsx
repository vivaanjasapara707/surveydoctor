import { Button } from '../components/Button'

const CHECKS: { name: string; what: string }[] = [
  {
    name: 'Careless responding',
    what: 'Answers that look random, repeated or rushed, each flagged with its reason.',
  },
  { name: 'Reliability', what: 'Whether the questions of each scale hang together.' },
  { name: 'Structure', what: 'Whether the questions group into the scales you declared.' },
  { name: 'Sample size', what: 'The smallest effect your sample can reliably detect.' },
  {
    name: 'Robustness',
    what: 'Whether your main result changes when doubtful respondents are left out.',
  },
]

interface LandingProps {
  onSample: () => void
  onUpload: () => void
}

export function Landing({ onSample, onUpload }: LandingProps) {
  return (
    <div className="max-w-measure space-y-12">
      <section>
        <h1 tabIndex={-1} className="text-verdict font-semibold">
          Check the quality of your survey data before you analyse it.
        </h1>
        <p className="mt-4 text-graphite">
          SurveyDoctor checks rating-scale survey responses for careless answers, weak scales and
          fragile results, and tells you plainly where to look.
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Button variant="primary" onClick={onSample}>
            Try with sample data
          </Button>
          <Button onClick={onUpload}>Upload your survey</Button>
        </div>
        <p className="mt-3 text-small text-slate">
          Works with a CSV file of rating answers (for example 1–5, or “Strongly agree”), up to 10
          MB.
        </p>
      </section>

      <section aria-labelledby="checks-heading">
        <h2 id="checks-heading" className="text-sub font-semibold">
          What it checks
        </h2>
        <dl className="mt-3 divide-y divide-rule border-y border-rule">
          {CHECKS.map((check) => (
            <div key={check.name} className="py-3 sm:grid sm:grid-cols-[12rem_1fr] sm:gap-4">
              <dt className="font-semibold">{check.name}</dt>
              <dd className="text-graphite">{check.what}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section aria-labelledby="export-heading">
        <h2 id="export-heading" className="text-sub font-semibold">
          Getting a CSV file from your form
        </h2>
        <div className="mt-3 grid gap-6 sm:grid-cols-2">
          <div>
            <h3 className="font-semibold">Google Forms</h3>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-graphite">
              <li>Open the form and go to the Responses tab.</li>
              <li>
                Open the menu (⋮) and choose{' '}
                <strong className="text-ink">Download responses (.csv)</strong>.
              </li>
              <li>If the download is a .zip file, open it and upload the .csv file inside.</li>
            </ol>
          </div>
          <div>
            <h3 className="font-semibold">Microsoft Forms</h3>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-graphite">
              <li>
                Open the form, go to the Responses tab and choose{' '}
                <strong className="text-ink">Open results in Excel</strong>.
              </li>
              <li>
                In Excel, save a copy as{' '}
                <strong className="text-ink">CSV UTF-8 (Comma delimited)</strong>.
              </li>
              <li>Upload that .csv file. Excel workbooks (.xlsx) are not accepted.</li>
            </ol>
          </div>
        </div>
      </section>

      <section aria-labelledby="privacy-heading">
        <h2 id="privacy-heading" className="text-sub font-semibold">
          Your data
        </h2>
        <p className="mt-3 text-graphite">
          Your file is sent to the SurveyDoctor server only to run the checks. It is processed in
          memory and discarded straight away; nothing is stored. Columns that look like names or
          email addresses are left out of the preview and of every result. What you see stays in
          this browser tab, and refreshing the page clears it.
        </p>
      </section>
    </div>
  )
}
