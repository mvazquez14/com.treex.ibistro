import { createFileRoute } from "@tanstack/react-router"

import { OnboardingWizard } from "@/pages/onboarding"

export const Route = createFileRoute("/onboarding")({
  component: OnboardingWizard,
})
