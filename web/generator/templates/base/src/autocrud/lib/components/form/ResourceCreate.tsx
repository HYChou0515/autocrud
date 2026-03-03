import { useRef } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Container, Title, Stack, Button, Group, Paper, Tabs } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import type { ResourceConfig, CustomCreateAction } from '../../resources';
import { ResourceForm, type ResourceFormHandle } from './ResourceForm';
import { showErrorNotification, extractUniqueConflict } from '../../utils/errorNotification';

export interface ResourceCreateProps<T> {
  config: ResourceConfig<T>;
  basePath: string;
}

/**
 * Generic resource create page.
 *
 * When the resource config contains `customCreateActions`, a tabbed
 * interface is rendered with "Standard" plus one tab per custom action.
 * Otherwise the standard single-form layout is used.
 */
export function ResourceCreate<T extends Record<string, any>>({
  config,
  basePath,
}: ResourceCreateProps<T>) {
  const navigate = useNavigate();
  const formRef = useRef<ResourceFormHandle | null>(null);
  const hasCustomActions =
    config.customCreateActions != null && config.customCreateActions.length > 0;

  const handleStandardSubmit = async (values: T) => {
    try {
      // Union resource: form wraps in { data: ... }, API expects the unwrapped union object
      const submitValues = config.isUnion ? ((values as any).data as T) : values;
      const result = await config.apiClient.create(submitValues);
      navigate({ to: `${basePath}/${result.data.resource_id}` });
    } catch (error) {
      const conflict = extractUniqueConflict(error);
      if (conflict && formRef.current) {
        formRef.current.setFieldError(conflict.field, `此值已被使用 (unique constraint)`);
        showErrorNotification(error, 'Create Failed');
      } else {
        showErrorNotification(error, 'Create Failed');
      }
    }
  };

  const makeCustomActionSubmit =
    (action: CustomCreateAction) => async (values: Record<string, any>) => {
      try {
        await action.apiMethod(values);
        navigate({ to: basePath });
      } catch (error) {
        showErrorNotification(error, `${action.label} Failed`);
      }
    };

  const standardForm = (
    <Paper withBorder p="md">
      <ResourceForm
        config={config}
        onSubmit={handleStandardSubmit}
        onCancel={() => navigate({ to: basePath })}
        submitLabel="Create"
        formRef={formRef}
      />
    </Paper>
  );

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <Group>
          <Button
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
            onClick={() => navigate({ to: basePath })}
          >
            Back
          </Button>
          <Title order={2}>Create {config.label}</Title>
        </Group>

        {hasCustomActions ? (
          <Tabs defaultValue="standard">
            <Tabs.List>
              <Tabs.Tab value="standard">Standard</Tabs.Tab>
              {config.customCreateActions!.map((action) => (
                <Tabs.Tab key={action.name} value={action.name}>
                  {action.label}
                </Tabs.Tab>
              ))}
            </Tabs.List>

            <Tabs.Panel value="standard" pt="md">
              {standardForm}
            </Tabs.Panel>

            {config.customCreateActions!.map((action) => (
              <Tabs.Panel key={action.name} value={action.name} pt="md">
                <Paper withBorder p="md">
                  <ResourceForm
                    config={{
                      ...config,
                      fields: action.fields,
                      zodSchema: action.zodSchema,
                      maxFormDepth: undefined,
                    }}
                    onSubmit={makeCustomActionSubmit(action)}
                    onCancel={() => navigate({ to: basePath })}
                    submitLabel={action.label}
                  />
                </Paper>
              </Tabs.Panel>
            ))}
          </Tabs>
        ) : (
          standardForm
        )}
      </Stack>
    </Container>
  );
}
