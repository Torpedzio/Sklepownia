import { router } from 'expo-router';
import { useState } from 'react';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { Icon, type IconName } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { Radius, Spacing } from '@/constants/theme';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { api } from '@/lib/api';
import { confirm } from '@/lib/confirm';
import { panelLocative, panelTitle } from '@/lib/format';
import { plural } from '@/lib/plural';
import type { ChecklistStepKey, ShopChecklist as Checklist, ShopDetail } from '@/lib/types';

const POLL_MS = 2500;

type Step = {
  title: string;
  description: string;
  action: { title: string; icon: IconName; onPress: () => void; variant?: 'primary' | 'secondary' };
};

type Props = {
  shop: ShopDetail;
  /** Opens a section of the shop's settings (as in the address: ?section=…). */
  onOpenSettings: (section: string) => void;
};

/**
 * The start checklist on a new shop's screen: what's left before the shop sells. The platform ticks the steps off
 * from what it sees in the shop, so the list has no checkboxes of its own. One step is open at a time.
 */
export function ShopChecklist({ shop, onOpenSettings }: Props) {
  const theme = useTheme();
  const notify = useNotify();
  const path = `/shops/${shop.id}/checklist/`;
  const { data, refresh } = useApiQuery<Checklist>(path, {
    refetchInterval: (current) => (current?.refreshing ? POLL_MS : false),
  });
  const [opened, setOpened] = useState<ChecklistStepKey | null>(null);
  const [busy, setBusy] = useState<'hide' | 'samples' | null>(null);

  if (!data?.available || !data.steps.length) return null;

  async function hide(ask: boolean) {
    if (
      ask &&
      !(await confirm(
        'Ukryć listę startową?',
        'Zniknie z ekranu sklepu. Kroki, których jeszcze nie ma, zrobisz dalej w ustawieniach i w panelu.',
        'Ukryj',
      ))
    )
      return;
    setBusy('hide');
    try {
      await api(path, { method: 'PATCH', body: { hidden: true } });
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function removeSamples() {
    const confirmed = await confirm(
      'Usunąć przykładowe produkty?',
      'Produkty „Przykładowy produkt” znikną ze sklepu. Twoich produktów nie ruszymy. Tego nie da się cofnąć.',
      'Usuń',
    );
    if (!confirmed) return;
    setBusy('samples');
    try {
      await api(`/shops/${shop.id}/remove-sample-products/`, { method: 'POST' });
      notify.success('Usuwamy przykładowe produkty. Krok odhaczy się za chwilę.');
      await refresh();
    } catch (e) {
      notify.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  const done = data.steps.filter((step) => step.done).length;
  const total = data.steps.length;

  if (done === total) {
    return (
      <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
        <View style={styles.row}>
          <Check done />
          <ThemedText type="heading" style={styles.flex}>
            Sklep jest gotowy do sprzedaży
          </ThemedText>
        </View>
        <ThemedText type="small" themeColor="textSecondary">
          Wszystkie kroki z listy startowej są zrobione. Listę możesz już ukryć.
        </ThemedText>
        <Button
          title="Ukryj listę"
          variant="secondary"
          loading={busy === 'hide'}
          onPress={() => hide(false)}
          style={styles.start}
        />
      </View>
    );
  }

  const samples = data.sample_products;
  const steps: Record<ChecklistStepKey, Step> = {
    payments: {
      title: 'Ustaw płatności',
      description: 'Przelew tradycyjny albo płatność przy odbiorze. Bez tego klienci nie zapłacą za zamówienie.',
      action: { title: 'Ustaw płatności', icon: 'card', onPress: () => onOpenSettings('platnosci') },
    },
    shipping: {
      title: 'Ustaw wysyłkę',
      description: 'Kurier, darmowa dostawa od wybranej kwoty albo odbiór osobisty. Klient wybierze jedną z nich.',
      action: { title: 'Ustaw wysyłkę', icon: 'truck', onPress: () => onOpenSettings('wysylka') },
    },
    products: {
      title: 'Dodaj pierwszy produkt',
      description:
        `Zdjęcia, opis i cenę dodasz w ${panelLocative(shop.panel_name)}. ` +
        'Zauważymy produkt, gdy wrócisz do aplikacji.',
      action: { title: panelTitle(shop.panel_name), icon: 'admin', onPress: () => onOpenSettings('reczne') },
    },
    sample_products: {
      title: 'Usuń przykładowe produkty',
      description: samples
        ? `W sklepie ${plural(samples, ['jest', 'są', 'jest'])} jeszcze ${samples} ${plural(samples, [
            'przykładowy produkt',
            'przykładowe produkty',
            'przykładowych produktów',
          ])} z zakładania. Usuń je, zanim pokażesz sklep klientom.`
        : 'Produkty dodane przy zakładaniu sklepu. Usuń je, zanim pokażesz sklep klientom.',
      action: { title: 'Usuń przykładowe', icon: 'trash', variant: 'secondary', onPress: removeSamples },
    },
    notifications: {
      title: 'Włącz powiadomienia',
      description: 'O nowym zamówieniu dowiesz się od razu, w aplikacji na telefonie.',
      action: { title: 'Włącz powiadomienia', icon: 'bell', onPress: () => router.push('/notifications') },
    },
    test_order: {
      title: 'Złóż próbne zamówienie',
      description: 'Kup coś we własnym sklepie, żeby sprawdzić koszyk, płatność i dostawę. Potem anulujesz je w panelu.',
      action: { title: 'Otwórz sklep', icon: 'external', onPress: () => Linking.openURL(shop.url) },
    },
  };

  // The step tapped last while it's still to do, or else the next one.
  const open = data.steps.filter((step) => !step.done);
  const expanded = (open.find((step) => step.key === opened) ?? open[0]).key;

  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <View style={styles.row}>
        <View style={styles.flex}>
          <ThemedText type="heading">Lista startowa</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {data.refreshing ? 'Sprawdzamy sklep…' : 'Kroki odhaczają się same, gdy coś zmienisz w sklepie.'}
          </ThemedText>
        </View>
        <ThemedText type="smallBold">
          {done} z {total}
        </ThemedText>
      </View>
      <Progress done={done} total={total} />
      <View>
        {data.steps.map((step, index) => (
          <StepRow
            key={step.key}
            step={steps[step.key]}
            done={step.done}
            expanded={step.key === expanded}
            first={index === 0}
            busy={step.key === 'sample_products' && busy === 'samples'}
            onOpen={() => setOpened(step.key)}
          />
        ))}
      </View>
      <Button
        title="Ukryj listę"
        variant="ghost"
        loading={busy === 'hide'}
        onPress={() => hide(true)}
        style={[styles.start, styles.flush]}
      />
    </View>
  );
}

type StepRowProps = {
  step: Step;
  done: boolean;
  expanded: boolean;
  first: boolean;
  busy: boolean;
  onOpen: () => void;
};

function StepRow({ step, done, expanded, first, busy, onOpen }: StepRowProps) {
  const theme = useTheme();
  return (
    <View style={[styles.step, !first && { borderTopWidth: 1, borderTopColor: theme.border }]}>
      <Pressable
        accessibilityRole={done ? 'text' : 'button'}
        accessibilityLabel={done ? `${step.title}: zrobione` : step.title}
        accessibilityState={done ? undefined : { expanded }}
        disabled={done || expanded}
        onPress={onOpen}
        style={styles.row}>
        <Check done={done} />
        <ThemedText
          type={expanded ? 'smallBold' : 'small'}
          themeColor={done ? 'textSecondary' : 'text'}
          style={styles.flex}>
          {step.title}
        </ThemedText>
        {!done && !expanded ? <Icon name="chevronDown" size={16} color="textSecondary" /> : null}
      </Pressable>
      {expanded ? (
        <View style={styles.stepBody}>
          <ThemedText type="small" themeColor="textSecondary">
            {step.description}
          </ThemedText>
          <Button
            title={step.action.title}
            icon={step.action.icon}
            variant={step.action.variant ?? 'primary'}
            loading={busy}
            onPress={step.action.onPress}
            style={styles.start}
          />
        </View>
      ) : null}
    </View>
  );
}

/** A filled circle with a tick once the step is done; an empty ring before. */
function Check({ done = false }: { done?: boolean }) {
  const theme = useTheme();
  if (!done) return <View style={[styles.check, { borderColor: theme.textSecondary }]} />;
  return (
    <View style={[styles.check, { backgroundColor: theme.success, borderColor: theme.success }]}>
      <Icon name="check" size={13} tintColor={theme.surface} />
    </View>
  );
}

function Progress({ done, total }: { done: number; total: number }) {
  const theme = useTheme();
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel="Zrobione kroki"
      accessibilityValue={{ min: 0, max: total, now: done, text: `${done} z ${total}` }}
      style={[styles.track, { backgroundColor: theme.surfaceMuted }]}>
      <View style={[styles.fill, { width: `${(done / total) * 100}%`, backgroundColor: theme.success }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  start: {
    alignSelf: 'flex-start',
  },
  // A ghost button's text lines up with the steps above it.
  flush: {
    marginLeft: -Spacing.four,
    marginTop: -Spacing.two,
  },
  track: {
    height: 6,
    borderRadius: 3,
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 3,
  },
  step: {
    gap: Spacing.two,
    paddingVertical: Spacing.three,
  },
  stepBody: {
    gap: Spacing.three,
    // Under the title, past the circle.
    paddingLeft: 22 + Spacing.two,
  },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
