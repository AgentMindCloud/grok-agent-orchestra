import { LoginForm } from "@/components/login-form";

export const metadata = {
  title: "Sign in · Agent Orchestra",
  description: "Authenticate to access the Agent Orchestra dashboard.",
};

interface LoginPageProps {
  searchParams: { next?: string };
}

export default function LoginPage({ searchParams }: LoginPageProps): JSX.Element {
  return (
    <div className="mx-auto flex min-h-[60vh] max-w-md flex-col justify-center">
      <div className="space-y-6">
        <div className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold tracking-tight">Welcome back</h1>
          <p className="text-sm text-muted-foreground">
            This Agent Orchestra instance has shared-password auth enabled.
            Enter the password your operator set in
            <code className="mx-1 rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              GROK_ORCHESTRA_AUTH_PASSWORD
            </code>
            to continue.
          </p>
        </div>
        <LoginForm next={searchParams.next ?? "/"} />
      </div>
    </div>
  );
}
