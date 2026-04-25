import Link from "next/link";

import { Button } from "@/components/ui/button";

export const metadata = {
  title: "Not found · Agent Orchestra",
  description: "The page you’re looking for doesn’t exist.",
};

export default function NotFound(): JSX.Element {
  return (
    <div className="mx-auto flex min-h-[50vh] max-w-md flex-col items-center justify-center gap-4 text-center">
      <p className="text-6xl font-semibold tracking-tight text-primary">404</p>
      <div className="space-y-1.5">
        <h1 className="text-xl font-semibold tracking-tight">
          That page is off the score.
        </h1>
        <p className="text-sm text-muted-foreground">
          Try the dashboard, or browse the templates.
        </p>
      </div>
      <div className="flex gap-2">
        <Button asChild>
          <Link href="/">Dashboard</Link>
        </Button>
        <Button asChild variant="outline">
          <Link href="/templates">Templates</Link>
        </Button>
      </div>
    </div>
  );
}
