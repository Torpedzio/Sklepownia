const POLISH: Record<string, string> = { ą: 'a', ć: 'c', ę: 'e', ł: 'l', ń: 'n', ó: 'o', ś: 's', ź: 'z', ż: 'z' };

export function slugify(text: string) {
  return text
    .toLowerCase()
    .replace(/[ąćęłńóśźż]/g, (char) => POLISH[char])
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 30)
    .replace(/^-+|-+$/g, '');
}
