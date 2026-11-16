import { Link } from 'expo-router';

import { Button } from '@/components/ui/button';
import { useAuth } from '@/context/auth';
import type { Plan } from '@/lib/types';

/** The next step under a plan card, depending on who looks: sign up, confirm the e-mail, choose, or manage. */
export function PlanAction({ plan }: { plan: Plan }) {
  const { user } = useAuth();
  if (!user) {
    return (
      <Link href="/sign-up" asChild>
        <Button title="Załóż konto" size="large" />
      </Link>
    );
  }
  if (!user.is_email_verified) {
    return (
      <Link href="/verify-email" asChild>
        <Button title="Potwierdź e-mail, żeby wybrać plan" size="large" />
      </Link>
    );
  }
  if (user.plan) {
    return (
      <Link href="/billing" asChild>
        <Button title="Plan i płatności" variant="secondary" size="large" />
      </Link>
    );
  }
  return (
    <Link href={{ pathname: '/billing/checkout', params: { plan: plan.code } }} asChild>
      <Button title="Wybierz plan" size="large" />
    </Link>
  );
}
