import type { ReactNode } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { Icon } from '@/components/icon';
import { ThemedText } from '@/components/themed-text';
import { Radius, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { formatMoney } from '@/lib/format';
import { plural } from '@/lib/plural';
import type { Plan } from '@/lib/types';

type PlanCardProps = {
  plan: Plan;
  /** Pickable card (checkout): shows whether it is the chosen plan. */
  selected?: boolean;
  onSelect?: () => void;
  /** E.g. a button under the benefits (pricing page). */
  children?: ReactNode;
};

export function periodLabel(months: number) {
  return months === 1
    ? 'miesiąc'
    : months === 12
      ? 'rok'
      : `${months} ${plural(months, ['miesiąc', 'miesiące', 'miesięcy'])}`;
}

/** "1 sklep", "do 3 sklepów, w tym 1 na Magento", "do 10 sklepów, w tym do 5 na Magento". */
export function planShopsLabel(plan: Pick<Plan, 'max_shops' | 'max_magento_shops'>) {
  const shops = plan.max_shops === 1 ? '1 sklep' : `do ${plan.max_shops} sklepów`;
  const magento = plan.max_magento_shops;
  if (!magento) return shops;
  return `${shops}, w tym ${magento === 1 || magento === plan.max_shops ? magento : `do ${magento}`} na Magento`;
}

/** A plan with its gross price and benefits. */
export function PlanCard({ plan, selected, onSelect, children }: PlanCardProps) {
  const theme = useTheme();
  const content = (
    <>
      <View style={styles.head}>
        <ThemedText type="subtitle" style={styles.flex}>
          {plan.name}
        </ThemedText>
        {plan.is_featured ? (
          <View style={[styles.featured, { backgroundColor: theme.accent }]}>
            <ThemedText type="smallBold" style={{ color: theme.onAccent }}>
              Polecany
            </ThemedText>
          </View>
        ) : null}
        {onSelect ? (
          <Icon
            name={selected ? 'check' : 'plus'}
            size={20}
            tintColor={selected ? theme.primary : theme.textSecondary}
          />
        ) : null}
      </View>
      <View style={styles.price}>
        <ThemedText type="title">{formatMoney(plan.price, plan.currency)}</ThemedText>
        <ThemedText themeColor="textSecondary"> / {periodLabel(plan.interval_months)}</ThemedText>
      </View>
      {plan.description ? <ThemedText themeColor="textSecondary">{plan.description}</ThemedText> : null}
      <View style={styles.features}>
        {plan.features.map((feature) => (
          <View key={feature} style={styles.feature}>
            <Icon name="check" size={16} color="primary" />
            <ThemedText type="small" style={styles.flex}>
              {feature}
            </ThemedText>
          </View>
        ))}
      </View>
      {children}
    </>
  );
  const style = [
    styles.card,
    {
      backgroundColor: selected ? theme.primaryMuted : theme.surface,
      borderColor: selected || (selected === undefined && plan.is_featured) ? theme.primary : theme.border,
    },
  ];
  if (!onSelect) return <View style={style}>{content}</View>;
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      accessibilityLabel={`${plan.name}${plan.is_featured ? ', polecany' : ''}, ${formatMoney(plan.price, plan.currency)} za ${periodLabel(plan.interval_months)}`}
      onPress={onSelect}
      style={style}>
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  card: {
    flexBasis: 280,
    flexGrow: 1,
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1.5,
  },
  head: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  price: {
    flexDirection: 'row',
    alignItems: 'baseline',
    flexWrap: 'wrap',
  },
  features: {
    gap: Spacing.two,
    // Side by side, cards are as tall as the tallest; their buttons line up at the bottom.
    flexGrow: 1,
  },
  featured: {
    paddingHorizontal: Spacing.two + Spacing.one,
    paddingVertical: Spacing.half,
    borderRadius: Radius.pill,
  },
  feature: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.two,
  },
});
