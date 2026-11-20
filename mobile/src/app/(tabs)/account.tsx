import Constants from 'expo-constants';
import { Link, type Href } from 'expo-router';
import { useState, type ReactNode } from 'react';
import { ActivityIndicator, Platform, Pressable, StyleSheet, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Avatar } from '@/components/avatar';
import { Awning } from '@/components/awning';
import { Icon, type IconName } from '@/components/icon';
import { Page } from '@/components/page';
import { ThemedText } from '@/components/themed-text';
import { Button } from '@/components/ui/button';
import { TextField } from '@/components/ui/text-field';
import { Radius, Spacing, WideBreakpoint, type ThemeColor } from '@/constants/theme';
import { useAuth } from '@/context/auth';
import { useNotify } from '@/context/notifications';
import { useApiQuery } from '@/hooks/use-api-query';
import { useTheme } from '@/hooks/use-theme';
import { useWindowDimensions } from '@/hooks/use-window-dimensions';
import { ApiError } from '@/lib/api';
import { pickAvatar } from '@/lib/avatar';
import { confirm } from '@/lib/confirm';
import { formatDate, formatMoney } from '@/lib/format';
import { plural } from '@/lib/plural';
import type { BillingOverview, Shop, User } from '@/lib/types';

export default function AccountScreen() {
  const { user, signOut } = useAuth();
  const notify = useNotify();
  const theme = useTheme();
  const { width } = useWindowDimensions();
  const wide = width >= WideBreakpoint;
  const { data: shops } = useApiQuery<Shop[]>('/shops/', { enabled: !!user });
  const { data: billing } = useApiQuery<BillingOverview>('/billing/', { enabled: !!user?.is_email_verified });

  if (!user) return null;

  async function handleSignOut() {
    await signOut();
    notify.success('Wylogowano.');
  }

  return (
    <SafeAreaView
      style={[styles.flex, { backgroundColor: theme.background }]}
      edges={Platform.OS === 'web' ? [] : ['top']}>
      <Page maxWidth={1040}>
        <ProfileCard user={user} />

        <View style={[styles.columns, wide && styles.columnsWide]}>
          <View style={[styles.column, wide && styles.mainColumn]}>
            <Overview user={user} shops={shops} billing={billing} />
            <ProfileForm user={user} />
            <Security />
          </View>

          <View style={[styles.column, wide && styles.sideColumn]}>
            <Card title="Na skróty">
              <View>
                <LinkRow href="/shops" icon="store" label="Twoje sklepy" />
                <LinkRow href="/billing" icon="card" label="Plan i płatności" />
                <LinkRow href="/notifications" icon="bell" label="Powiadomienia" />
                <LinkRow href="/help" icon="help" label="Porady i pomoc" />
                <LinkRow href="/pricing" icon="percent" label="Cennik" />
                <LinkRow href="/about" icon="category" label="Jak to działa" />
                <LinkRow href="/contact" icon="mail" label="Kontakt" last />
              </View>
            </Card>
            <Button title="Wyloguj się" variant="danger" icon="logout" onPress={handleSignOut} />
            <ThemedText type="small" themeColor="textSecondary" style={styles.version}>
              Wersja {Constants.expoConfig?.version}
            </ThemedText>
          </View>
        </View>
      </Page>
    </SafeAreaView>
  );
}

function ProfileCard({ user }: { user: User }) {
  const theme = useTheme();
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ');
  return (
    <View style={[styles.profileCard, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <Awning tone="card" />
      <View style={styles.profile}>
        <EditableAvatar user={user} />
        <View style={styles.profileText}>
          <ThemedText type="title" numberOfLines={1}>
            {name || 'Twoje konto'}
          </ThemedText>
          <ThemedText themeColor="textSecondary" numberOfLines={1}>
            {user.email}
          </ThemedText>
          <View style={styles.badges}>
            <Badge
              icon={user.is_email_verified ? 'check' : 'warning'}
              label={user.is_email_verified ? 'E-mail potwierdzony' : 'E-mail niepotwierdzony'}
              tone={user.is_email_verified ? ['success', 'primaryMuted'] : ['warning', 'accentMuted']}
            />
            <Badge
              icon="card"
              label={user.plan ? `Plan ${user.plan}` : user.purpose === 'team' ? 'Konto zespołu' : 'Bez planu'}
              tone={user.plan ? ['primary', 'primaryMuted'] : ['textSecondary', 'surfaceMuted']}
            />
            <Badge
              icon="clock"
              label={`Z nami od ${formatDate(user.date_joined)}`}
              tone={['textSecondary', 'surfaceMuted']}
            />
          </View>
        </View>
      </View>
    </View>
  );
}

/** Tapping opens the photo library; the new picture uploads straight away. */
function EditableAvatar({ user }: { user: User }) {
  const theme = useTheme();
  const notify = useNotify();
  const { changeAvatar, removeAvatar } = useAuth();
  const [busy, setBusy] = useState(false);

  async function run(action: () => Promise<string | null>) {
    setBusy(true);
    try {
      const message = await action();
      if (message) notify.success(message);
    } catch (e) {
      notify.error(e instanceof ApiError ? (e.fieldErrors.avatar ?? e.message) : (e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const change = () =>
    run(async () => {
      const file = await pickAvatar();
      if (!file) return null;
      await changeAvatar(file);
      return 'Zdjęcie profilowe zmienione.';
    });

  const remove = () =>
    run(async () => {
      if (!(await confirm('Usunąć zdjęcie profilowe?', 'Zamiast niego pokażemy pierwszą literę imienia.', 'Usuń'))) {
        return null;
      }
      await removeAvatar();
      return 'Zdjęcie profilowe usunięte.';
    });

  return (
    <View style={styles.avatarColumn}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={user.avatar_url ? 'Zmień zdjęcie profilowe' : 'Dodaj zdjęcie profilowe'}
        accessibilityState={{ busy }}
        disabled={busy}
        onPress={change}>
        {({ hovered, pressed }) => (
          <View>
            <Avatar user={user} size={AVATAR_SIZE} />
            {busy || hovered || pressed ? (
              <View style={styles.avatarOverlay}>
                {busy ? <ActivityIndicator color="#FFFFFF" /> : <Icon name="camera" size={26} tintColor="#FFFFFF" />}
              </View>
            ) : null}
            <View style={[styles.avatarBadge, { backgroundColor: theme.surface, borderColor: theme.border }]}>
              <Icon name="camera" size={15} color="primary" />
            </View>
          </View>
        )}
      </Pressable>
      {user.avatar_url ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Usuń zdjęcie profilowe"
          disabled={busy}
          onPress={remove}
          hitSlop={Spacing.two}
          style={({ hovered }) => (hovered ? styles.removeHovered : undefined)}>
          <ThemedText type="small" themeColor="textSecondary">
            Usuń
          </ThemedText>
        </Pressable>
      ) : null}
    </View>
  );
}

const AVATAR_SIZE = 80;

function Badge({ icon, label, tone }: { icon: IconName; label: string; tone: [ThemeColor, ThemeColor] }) {
  const theme = useTheme();
  const [color, background] = tone;
  return (
    <View style={[styles.badge, { backgroundColor: theme[background] }]}>
      <Icon name={icon} size={14} color={color} />
      <ThemedText type="smallBold" themeColor={color}>
        {label}
      </ThemedText>
    </View>
  );
}

function Overview({
  user,
  shops,
  billing,
}: {
  user: User;
  shops: Shop[] | undefined;
  billing: BillingOverview | undefined;
}) {
  // Shops served in others' teams are on their owners' plans.
  const own = shops?.filter((shop) => shop.role === 'owner') ?? [];
  const served = (shops?.length ?? 0) - own.length;
  const paid = own.filter((shop) => !shop.is_test);
  const counted = paid.filter((shop) => shop.status !== 'suspended');
  const suspended = paid.length - counted.length;
  // Only some of a plan's shops may run on Magento; show that count once there is one.
  const magento = counted.filter((shop) => shop.platform === 'magento').length;
  const magentoNote =
    user.plan && magento && user.magento_shop_limit ? `W tym ${magento} z ${user.magento_shop_limit} na Magento` : '';
  const tests = own.length - paid.length;
  const subscription = billing?.subscription;
  const running = subscription && ['active', 'past_due'].includes(subscription.status);
  const profile = billing?.profile;

  const shopNotes = [
    suspended ? `${suspended} ${plural(suspended, ['zawieszony', 'zawieszone', 'zawieszonych'])}` : '',
    tests ? `${tests} ${plural(tests, ['testowy', 'testowe', 'testowych'])} poza planem` : '',
    served ? `${served} ${plural(served, ['obsługiwany', 'obsługiwane', 'obsługiwanych'])} w zespole` : '',
  ].filter(Boolean);

  // A team account serves others' shops; their owners pay.
  const joining = user.purpose === 'team' && !user.plan;
  let planNote = joining ? 'Sklepy w zespole opłaca ich właściciel' : 'Wybierz plan, żeby zakładać sklepy';
  if (running && subscription.status === 'past_due') {
    planNote = 'Zaległa płatność: sprawdź kartę';
  } else if (running && subscription.cancel_at_period_end && subscription.current_period_end) {
    planNote = `Działa do ${formatDate(subscription.current_period_end)}`;
  } else if (running && subscription.current_period_end) {
    const due = Math.max(Number(subscription.plan.price) - Number(subscription.credit), 0);
    planNote = `Następna płatność ${formatDate(subscription.current_period_end)}: ${formatMoney(due, subscription.plan.currency)}`;
  }

  return (
    <Card title="Twoje konto w skrócie">
      <View style={styles.tiles}>
        <Tile
          href="/shops"
          icon="store"
          title="Sklepy"
          value={
            shops === undefined
              ? '…'
              : user.plan
                ? `${counted.length} z ${user.shop_limit} w planie`
                : `${shops.length} ${plural(shops.length, ['sklep', 'sklepy', 'sklepów'])}`
          }
          note={[
            magentoNote,
            shopNotes.join(', ') ||
              (user.plan ? 'Wszystkie działają' : joining ? 'Czekasz na zaproszenie' : 'Wybierz plan, żeby założyć nowy'),
          ]
            .filter(Boolean)
            .join('. ')}
        />
        <Tile
          href="/billing"
          icon="card"
          title="Plan"
          value={running ? subscription.plan.name : 'Brak planu'}
          note={planNote}
          warning={subscription?.status === 'past_due'}
        />
        <Tile
          href="/billing"
          icon="category"
          title="Dane do faktury"
          value={profile ? (profile.kind === 'company' ? profile.company_name : profile.full_name) : 'Nie podano'}
          note={
            profile
              ? profile.kind === 'company'
                ? `NIP ${profile.tax_id}`
                : `${profile.postal_code} ${profile.city}`
              : 'Uzupełnisz przy wyborze planu'
          }
        />
      </View>
    </Card>
  );
}

type TileProps = { href: Href; icon: IconName; title: string; value: string; note: string; warning?: boolean };

function Tile({ href, icon, title, value, note, warning }: TileProps) {
  const theme = useTheme();
  return (
    <Link href={href} asChild>
      <Pressable
        accessibilityRole="link"
        accessibilityLabel={`${title}: ${value}. ${note}`}
        // Link's asChild takes only a plain style object (no arrays, no functions).
        style={StyleSheet.flatten([
          styles.tile,
          { backgroundColor: theme.background, borderColor: warning ? theme.accent : theme.border },
        ])}>
        <View style={styles.tileHead}>
          <Icon name={warning ? 'warning' : icon} size={18} tintColor={warning ? theme.warning : theme.textSecondary} />
          <ThemedText type="small" themeColor="textSecondary" style={styles.flex}>
            {title}
          </ThemedText>
          <Icon name="chevron" size={16} color="textSecondary" />
        </View>
        <ThemedText type="heading" numberOfLines={1}>
          {value}
        </ThemedText>
        <ThemedText type="small" themeColor={warning ? 'text' : 'textSecondary'}>
          {note}
        </ThemedText>
      </Pressable>
    </Link>
  );
}

function ProfileForm({ user }: { user: User }) {
  const { updateProfile } = useAuth();
  const notify = useNotify();
  const [firstName, setFirstName] = useState(user.first_name);
  const [lastName, setLastName] = useState(user.last_name);
  const [saving, setSaving] = useState(false);
  const changed = firstName !== user.first_name || lastName !== user.last_name;

  async function handleSave() {
    setSaving(true);
    try {
      await updateProfile({ first_name: firstName.trim(), last_name: lastName.trim() });
      notify.success('Zapisano zmiany w profilu.');
    } catch (e) {
      notify.error(e instanceof ApiError ? e.message : 'Nie udało się zapisać zmian.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Dane profilu" description="Imię pokazujemy na liście sklepów i w wiadomościach od nas.">
      <View style={styles.fields}>
        <View style={styles.field}>
          <TextField label="Imię" value={firstName} onChangeText={setFirstName} autoComplete="given-name" />
        </View>
        <View style={styles.field}>
          <TextField label="Nazwisko" value={lastName} onChangeText={setLastName} autoComplete="family-name" />
        </View>
      </View>
      <View style={styles.readOnly}>
        <ThemedText type="smallBold">E-mail</ThemedText>
        <ThemedText>{user.email}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          Na ten adres wysyłamy dane logowania do sklepów i potwierdzenia płatności.
        </ThemedText>
      </View>
      <Button title="Zapisz zmiany" onPress={handleSave} loading={saving} disabled={!changed} style={styles.start} />
    </Card>
  );
}

function Security() {
  const { changePassword, signOutEverywhere } = useAuth();
  const notify = useNotify();
  const [editing, setEditing] = useState(false);
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);

  function close() {
    setEditing(false);
    setCurrent('');
    setNext('');
    setErrors({});
  }

  async function handleChange() {
    setSaving(true);
    setErrors({});
    try {
      await changePassword(current, next);
      close();
      notify.success('Hasło zmienione. Na innych urządzeniach trzeba zalogować się ponownie.');
    } catch (e) {
      if (e instanceof ApiError) setErrors(e.fieldErrors);
      notify.error(e instanceof ApiError && e.status === 400 ? 'Popraw zaznaczone pola.' : (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOutEverywhere() {
    const confirmed = await confirm(
      'Wylogować wszędzie?',
      'Wylogujemy Cię na wszystkich urządzeniach, także na tym. Sklepy działają dalej.',
      'Wyloguj wszędzie',
    );
    if (!confirmed) return;
    try {
      await signOutEverywhere();
      notify.success('Wylogowano ze wszystkich urządzeń.');
    } catch (e) {
      notify.error((e as Error).message);
    }
  }

  return (
    <Card title="Bezpieczeństwo">
      <Setting
        title="Hasło"
        description="Po zmianie wylogujemy pozostałe urządzenia i wyślemy Ci e-mail z potwierdzeniem.">
        {editing ? null : (
          <Button title="Zmień hasło" variant="secondary" icon="shield" onPress={() => setEditing(true)} />
        )}
      </Setting>
      {editing ? (
        <View style={styles.passwordForm}>
          <TextField
            label="Obecne hasło"
            value={current}
            onChangeText={setCurrent}
            error={errors.current_password}
            secureTextEntry
            autoComplete="current-password"
            textContentType="password"
          />
          <TextField
            label="Nowe hasło"
            value={next}
            onChangeText={setNext}
            error={errors.new_password}
            hint="Co najmniej 8 znaków, nie same cyfry."
            secureTextEntry
            autoComplete="new-password"
            textContentType="newPassword"
            onSubmitEditing={handleChange}
          />
          <View style={styles.buttons}>
            <Button
              title="Zapisz nowe hasło"
              icon="check"
              loading={saving}
              disabled={!current || !next}
              onPress={handleChange}
            />
            <Button title="Anuluj" variant="ghost" onPress={close} disabled={saving} />
          </View>
        </View>
      ) : null}
      <Setting
        title="Wylogowanie ze wszystkich urządzeń"
        description="Przyda się, gdy aplikacja została zalogowana na cudzym komputerze albo zginął telefon.">
        <Button title="Wyloguj wszędzie" variant="secondary" icon="logout" onPress={handleSignOutEverywhere} />
      </Setting>
      <Setting
        title="Usunięcie konta"
        description="Usuwa konto razem ze sklepami i planem. Najpierw pokażemy, co dokładnie zniknie.">
        <Link href="/delete-account" asChild>
          <Button title="Usuń konto" variant="danger" icon="trash" />
        </Link>
      </Setting>
    </Card>
  );
}

function Setting({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <View style={styles.setting}>
      <View style={styles.settingText}>
        <ThemedText type="smallBold">{title}</ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {description}
        </ThemedText>
      </View>
      {children}
    </View>
  );
}

function Card({ title, description, children }: { title: string; description?: string; children: ReactNode }) {
  const theme = useTheme();
  return (
    <View style={[styles.card, { backgroundColor: theme.surface, borderColor: theme.border }]}>
      <View style={styles.cardHead}>
        <ThemedText type="heading">{title}</ThemedText>
        {description ? (
          <ThemedText type="small" themeColor="textSecondary">
            {description}
          </ThemedText>
        ) : null}
      </View>
      {children}
    </View>
  );
}

type LinkRowProps = {
  href: '/shops' | '/billing' | '/notifications' | '/help' | '/pricing' | '/about' | '/contact';
  icon: IconName;
  label: string;
  last?: boolean;
};

function LinkRow({ href, icon, label, last }: LinkRowProps) {
  const theme = useTheme();
  return (
    <Link href={href} asChild>
      <Pressable
        accessibilityRole="link"
        // Link's asChild doesn't take a style array.
        style={StyleSheet.flatten([
          styles.linkRow,
          !last && { borderBottomWidth: 1, borderBottomColor: theme.border },
        ])}>
        <Icon name={icon} size={20} color="textSecondary" />
        <ThemedText style={styles.flex}>{label}</ThemedText>
        <Icon name="chevron" size={18} color="textSecondary" />
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  flex: {
    flex: 1,
  },
  start: {
    alignSelf: 'flex-start',
  },
  profileCard: {
    borderRadius: Radius.large,
    borderWidth: 1,
    overflow: 'hidden',
  },
  profile: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.four,
    padding: Spacing.four,
  },
  profileText: {
    flexBasis: 260,
    flexGrow: 1,
    gap: Spacing.one,
  },
  avatarColumn: {
    alignItems: 'center',
    gap: Spacing.one,
  },
  avatarOverlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0, 0, 0, 0.45)',
    borderRadius: Radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarBadge: {
    position: 'absolute',
    right: -2,
    bottom: -2,
    width: 30,
    height: 30,
    borderRadius: 15,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeHovered: {
    opacity: 0.6,
  },
  badges: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
    marginTop: Spacing.two,
  },
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one,
    paddingHorizontal: Spacing.two + Spacing.one,
    paddingVertical: Spacing.half + 1,
    borderRadius: Radius.pill,
  },
  columns: {
    gap: Spacing.four,
  },
  columnsWide: {
    flexDirection: 'row',
    alignItems: 'flex-start',
  },
  column: {
    gap: Spacing.four,
  },
  mainColumn: {
    flex: 1,
  },
  sideColumn: {
    width: 320,
  },
  card: {
    gap: Spacing.three,
    padding: Spacing.four,
    borderRadius: Radius.large,
    borderWidth: 1,
  },
  cardHead: {
    gap: Spacing.one,
  },
  tiles: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  tile: {
    flexBasis: 180,
    flexGrow: 1,
    gap: Spacing.one,
    padding: Spacing.three,
    borderRadius: Radius.medium,
    borderWidth: 1.5,
  },
  tileHead: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  fields: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.three,
  },
  field: {
    flexBasis: 200,
    flexGrow: 1,
  },
  readOnly: {
    gap: Spacing.one,
  },
  setting: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    gap: Spacing.three,
  },
  settingText: {
    flexBasis: 240,
    flexGrow: 1,
    gap: Spacing.half,
  },
  passwordForm: {
    gap: Spacing.three,
  },
  buttons: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.two,
  },
  linkRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.three,
    paddingVertical: Spacing.three,
  },
  version: {
    textAlign: 'center',
  },
});
