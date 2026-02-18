/**
 * UnionFieldRenderer — Renders discriminated and simple union fields.
 */

import {
  TextInput,
  NumberInput,
  Textarea,
  Select,
  Stack,
  Group,
  Switch,
  Text,
  Paper,
  Radio,
} from '@mantine/core';
import type { UseFormReturnType } from '@mantine/form';
import type { ResourceField, UnionMeta } from '../../resources';

interface UnionFieldRendererProps {
  field: ResourceField;
  unionMeta: UnionMeta;
  form: UseFormReturnType<any>;
  simpleUnionTypes: Record<string, string>;
  setSimpleUnionTypes: React.Dispatch<React.SetStateAction<Record<string, string>>>;
}

export function UnionFieldRenderer({
  field,
  unionMeta,
  form,
  simpleUnionTypes,
  setSimpleUnionTypes,
}: UnionFieldRendererProps) {
  const { name, label, isRequired } = field;
  const isDiscriminated = unionMeta.discriminatorField !== '__type';
  const currentValue = (form.getValues() as Record<string, any>)[name];

  if (isDiscriminated) {
    const discField = unionMeta.discriminatorField;
    const selectedTag = currentValue?.[discField] ?? '';
    const selectedVariant = unionMeta.variants.find((v) => v.tag === selectedTag);

    const handleVariantChange = (tag: string) => {
      const variant = unionMeta.variants.find((v) => v.tag === tag);
      if (!variant) return;
      const newValue: Record<string, any> = { [discField]: tag };
      if (variant.fields) {
        for (const sf of variant.fields) {
          if (sf.type === 'number') newValue[sf.name] = '';
          else if (sf.type === 'boolean') newValue[sf.name] = false;
          else if (sf.type === 'object') newValue[sf.name] = '';
          else newValue[sf.name] = '';
        }
      }
      form.setFieldValue(name as any, newValue as any);
    };

    return (
      <Stack key={name} gap="xs">
        <Radio.Group
          label={label}
          required={isRequired}
          value={selectedTag}
          onChange={handleVariantChange}
        >
          <Stack gap="xs" mt="xs">
            {unionMeta.variants.map((v) => (
              <Radio.Card key={v.tag} value={v.tag} radius="md" withBorder p="md">
                <Group wrap="nowrap" align="flex-start">
                  <Radio.Indicator />
                  <div>
                    <Text fw={500} size="sm">
                      {v.label}
                    </Text>
                    {v.schemaName && (
                      <Text size="xs" c="dimmed">
                        {v.schemaName}
                      </Text>
                    )}
                  </div>
                </Group>
              </Radio.Card>
            ))}
          </Stack>
        </Radio.Group>

        {selectedVariant?.fields && selectedVariant.fields.length > 0 && (
          <Paper withBorder p="sm" radius="sm">
            <Stack gap="xs">
              {selectedVariant.fields.map((sf) => {
                const subPath = `${name}.${sf.name}`;
                if (sf.enumValues && sf.enumValues.length > 0) {
                  return (
                    <Select
                      key={subPath}
                      label={sf.label}
                      required={sf.isRequired}
                      data={sf.enumValues.map((v) => ({ value: v, label: v }))}
                      clearable={sf.isNullable}
                      {...form.getInputProps(subPath)}
                    />
                  );
                }
                if (sf.type === 'boolean') {
                  return (
                    <Switch
                      key={subPath}
                      label={sf.label}
                      {...form.getInputProps(subPath, { type: 'checkbox' })}
                    />
                  );
                }
                if (sf.type === 'number') {
                  return (
                    <NumberInput
                      key={subPath}
                      label={sf.label}
                      required={sf.isRequired}
                      {...form.getInputProps(subPath)}
                    />
                  );
                }
                if (sf.type === 'object') {
                  return (
                    <Textarea
                      key={subPath}
                      label={sf.label}
                      required={sf.isRequired}
                      placeholder="{}"
                      minRows={2}
                      styles={{ input: { fontFamily: 'monospace', fontSize: '13px' } }}
                      {...form.getInputProps(subPath)}
                    />
                  );
                }
                return (
                  <TextInput
                    key={subPath}
                    label={sf.label}
                    required={sf.isRequired}
                    {...form.getInputProps(subPath)}
                  />
                );
              })}
            </Stack>
          </Paper>
        )}
      </Stack>
    );
  }

  // ── Simple union ──
  const inferType = (): string => {
    if (currentValue === null || currentValue === undefined || currentValue === '') {
      return simpleUnionTypes[name] || unionMeta.variants[0]?.tag || '';
    }
    if (typeof currentValue === 'number') return 'number';
    if (typeof currentValue === 'boolean') return 'boolean';
    return 'string';
  };
  const selectedType = inferType();

  const handleTypeChange = (tag: string) => {
    setSimpleUnionTypes((prev) => ({ ...prev, [name]: tag }));
    const variant = unionMeta.variants.find((v) => v.tag === tag);
    if (!variant) return;
    if (variant.type === 'number' || variant.type === 'integer') {
      form.setFieldValue(name as any, '' as any);
    } else if (variant.type === 'boolean') {
      form.setFieldValue(name as any, false as any);
    } else {
      form.setFieldValue(name as any, '' as any);
    }
  };

  const renderSimpleInput = () => {
    const variant = unionMeta.variants.find((v) => v.tag === selectedType);
    if (!variant) return null;
    if (variant.type === 'boolean') {
      return (
        <Switch label={`${label} value`} {...form.getInputProps(name, { type: 'checkbox' })} />
      );
    }
    if (variant.type === 'number' || variant.type === 'integer') {
      return (
        <NumberInput label={`${label} value`} required={isRequired} {...form.getInputProps(name)} />
      );
    }
    return (
      <TextInput label={`${label} value`} required={isRequired} {...form.getInputProps(name)} />
    );
  };

  return (
    <Stack key={name} gap="xs">
      <Radio.Group
        label={label}
        required={isRequired}
        value={selectedType}
        onChange={(val) => handleTypeChange(val)}
      >
        <Group mt="xs">
          {unionMeta.variants.map((v) => (
            <Radio key={v.tag} value={v.tag} label={v.label} />
          ))}
        </Group>
      </Radio.Group>
      {renderSimpleInput()}
    </Stack>
  );
}
