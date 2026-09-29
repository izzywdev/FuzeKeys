import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['build/**', 'dist-mfe/**'] },
  ...tseslint.configs.recommended,
  { rules: { '@typescript-eslint/no-explicit-any': 'off' } },
);
