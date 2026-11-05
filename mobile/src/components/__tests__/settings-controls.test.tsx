import { fireEvent, render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';

import { SettingsMenu, SettingsPane } from '@/components/settings-menu';
import { SettingsSection } from '@/components/settings-section';
import { ChipSelect } from '@/components/ui/chip-select';
import { SwitchRow } from '@/components/ui/switch-row';
import { TextField } from '@/components/ui/text-field';

describe('SwitchRow', () => {
  test('the whole row toggles the setting', async () => {
    const onChange = jest.fn();
    await render(
      <SwitchRow label="Opinie o produktach" description="Klienci oceniają" value={false} onChange={onChange} />,
    );

    await fireEvent.press(screen.getByRole('switch', { name: 'Opinie o produktach' }));

    expect(onChange).toHaveBeenCalledWith(true);
    expect(screen.getByText('Klienci oceniają')).toBeTruthy();
  });

  test('shows an error under the label', async () => {
    await render(<SwitchRow label="Zakupy bez konta" value onChange={jest.fn()} error="Wybierz jedno" />);

    expect(screen.getByText('Wybierz jedno')).toBeTruthy();
  });
});

describe('SettingsSection', () => {
  test('without edits there is nothing to save', async () => {
    await render(
      <SettingsSection title="Płatności" description="Sposoby zapłaty" onSave={jest.fn()} onUndo={jest.fn()}>
        <Text>pola</Text>
      </SettingsSection>,
    );

    expect(screen.getByText('Sposoby zapłaty')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Zapisz' })).toBeNull();
  });

  test('with edits it offers to save or undo them', async () => {
    const onSave = jest.fn();
    const onUndo = jest.fn();
    await render(
      <SettingsSection title="Płatności" dirty onSave={onSave} onUndo={onUndo}>
        <Text>pola</Text>
      </SettingsSection>,
    );

    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));
    await fireEvent.press(screen.getByRole('button', { name: 'Cofnij' }));

    expect(onSave).toHaveBeenCalled();
    expect(onUndo).toHaveBeenCalled();
  });

  test('waits while the shop is busy with another change', async () => {
    const onSave = jest.fn();
    await render(
      <SettingsSection title="Płatności" dirty waiting onSave={onSave} onUndo={jest.fn()}>
        <Text>pola</Text>
      </SettingsSection>,
    );

    expect(screen.getByText(/gdy sklep skończy wprowadzać poprzednie zmiany/)).toBeTruthy();
    await fireEvent.press(screen.getByRole('button', { name: 'Zapisz' }));
    expect(onSave).not.toHaveBeenCalled();
  });
});

describe('SettingsMenu', () => {
  const items = [
    { key: 'general', title: 'Podstawowe', icon: 'store' as const },
    { key: 'payments', title: 'Płatności', icon: 'card' as const, dirty: true },
  ];

  test.each([true, false])('selects a section (vertical: %p)', async (vertical) => {
    const onSelect = jest.fn();
    await render(<SettingsMenu items={items} active="general" onSelect={onSelect} vertical={vertical} />);

    expect(screen.getByRole('tab', { name: 'Podstawowe' })).toHaveProp('accessibilityState', { selected: true });
    await fireEvent.press(screen.getByRole('tab', { name: 'Płatności, niezapisane zmiany' }));

    expect(onSelect).toHaveBeenCalledWith('payments');
  });

  test('the pane shows the chosen section and swaps it', async () => {
    const order = ['general', 'payments'];
    await render(
      <SettingsPane active="general" order={order} vertical>
        <Text>Podstawowe</Text>
      </SettingsPane>,
    );
    expect(screen.getByText('Podstawowe')).toBeTruthy();

    await screen.rerender(
      <SettingsPane active="payments" order={order} vertical={false}>
        <Text>Płatności</Text>
      </SettingsPane>,
    );
    expect(screen.getByText('Płatności')).toBeTruthy();
  });
});

describe('form controls', () => {
  test('ChipSelect picks an option', async () => {
    const onChange = jest.fn();
    await render(
      <ChipSelect
        label="Waluta"
        options={[
          { value: 'PLN', label: 'Złoty' },
          { value: 'EUR', label: 'Euro' },
        ]}
        value="PLN"
        onChange={onChange}
        error="Wybierz walutę"
      />,
    );

    await fireEvent.press(screen.getByRole('radio', { name: 'Euro' }));

    expect(onChange).toHaveBeenCalledWith('EUR');
    expect(screen.getByText('Wybierz walutę')).toBeTruthy();
  });

  test('TextField shows a hint, or the error instead of it', async () => {
    const onChangeText = jest.fn();
    await render(<TextField label="Numer konta" hint="26 cyfr" value="" onChangeText={onChangeText} />);

    expect(screen.getByText('26 cyfr')).toBeTruthy();
    await fireEvent.changeText(screen.getByDisplayValue(''), '61 1090');
    expect(onChangeText).toHaveBeenCalledWith('61 1090');

    await screen.rerender(<TextField label="Numer konta" hint="26 cyfr" error="Błędny numer" value="" />);
    expect(screen.getByText('Błędny numer')).toBeTruthy();
    expect(screen.queryByText('26 cyfr')).toBeNull();
  });
});
