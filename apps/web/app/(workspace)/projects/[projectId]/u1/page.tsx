import { redirect } from "next/navigation";

export default async function ProjectU1CompatibilityPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  redirect(`/projects/${projectId}`);
}
