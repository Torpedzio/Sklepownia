import * as ImagePicker from 'expo-image-picker';

/** The backend's upload limit; it then stores the picture as a 512×512 square. */
export const MAX_AVATAR_BYTES = 10 * 1024 * 1024;

/** A web `File`, or what React Native's FormData takes for a file on the device. */
export type AvatarFile = Blob | { uri: string; name: string; type: string };

/** Opens the photo library with a square crop. Resolves to the chosen picture, or null when cancelled. */
export async function pickAvatar(): Promise<AvatarFile | null> {
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsEditing: true,
    aspect: [1, 1],
    quality: 0.85,
  });
  const asset = result.canceled ? undefined : result.assets[0];
  if (!asset) return null;
  if (asset.fileSize && asset.fileSize > MAX_AVATAR_BYTES) {
    throw new Error('Zdjęcie jest za duże. Wybierz plik do 10 MB.');
  }
  if (asset.file) return asset.file;
  return { uri: asset.uri, name: asset.fileName ?? 'avatar.jpg', type: asset.mimeType ?? 'image/jpeg' };
}

export function avatarForm(file: AvatarFile) {
  const form = new FormData();
  form.append('avatar', file as Blob);
  return form;
}
