import { createRoute } from '@tanstack/react-router'
import { ThemeToggle } from '@/components/theme-toggle'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { rootRoute } from './__root'

function TermsPage() {
  return (
    <div className="min-h-screen bg-background p-4 md:p-6">
      <div className="fixed top-3 right-3">
        <ThemeToggle />
      </div>
      <div className="mx-auto flex w-full max-w-3xl items-center justify-center py-10">
        <Card className="w-full">
          <CardHeader>
            <CardTitle>Terms of Use</CardTitle>
            <CardDescription>Rules and privacy details for platform participation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 text-sm leading-6 text-foreground">
            <section className="space-y-3">
              <p>
                This platform hosts research studies conducted by independent researchers. By
                accessing or participating in studies on this site, you agree to use the platform in
                a responsible manner.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-base font-semibold">Acceptable Use</h2>
              <p>
                You may not attempt to interfere with the operation of the platform or any studies
                hosted on it. This includes attempting to access data that does not belong to you,
                using automated scripts or bots to complete studies, attempting to reverse engineer
                study materials, or otherwise disrupting the system.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-base font-semibold">Independent Researchers</h2>
              <p>
                Studies hosted on this platform are created and managed by independent researchers.
                These researchers are responsible for the design of their studies, obtaining
                appropriate ethical approval (such as IRB approval), and providing informed consent
                information to participants.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-base font-semibold">Research Participation</h2>
              <p>
                Participation in any study is voluntary. Each study will provide its own informed
                consent document describing the purpose of the research, procedures, risks,
                benefits, and data handling practices.
              </p>
            </section>

            <section className="space-y-3">
              <h2 className="text-base font-semibold">Platform Availability</h2>
              <p>
                The platform is provided for research purposes and may occasionally be unavailable
                due to maintenance, updates, or technical issues.
              </p>
            </section>

            <section className="space-y-3 border-t pt-6">
              <h2 className="text-lg font-semibold">Privacy Notice</h2>
              <p>
                This platform hosts research studies conducted by independent researchers.
                Individual studies may collect research data as described in their informed consent
                documents.
              </p>
            </section>

            <section className="space-y-3">
              <h3 className="text-base font-semibold">Platform Data</h3>
              <p>
                To operate the platform and support research integrity, the system may collect
                limited technical information such as timestamps, browser or device information, IP
                address, and interaction logs related to study participation.
              </p>
            </section>

            <section className="space-y-3">
              <h3 className="text-base font-semibold">Research Data</h3>
              <p>
                Data collected within a study is determined by the researcher conducting that study
                and will be described in the study&apos;s informed consent document.
              </p>
            </section>

            <section className="space-y-3">
              <h3 className="text-base font-semibold">Use of Information</h3>
              <p>
                Platform data is used to operate the system, troubleshoot technical issues, and help
                ensure the quality and integrity of research data.
              </p>
            </section>

            <section className="space-y-3">
              <h3 className="text-base font-semibold">Contact</h3>
              <p>
                Questions about a specific study should be directed to the researcher listed in that
                study&apos;s consent form.
              </p>
            </section>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

export const termsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/terms',
  component: TermsPage,
})
