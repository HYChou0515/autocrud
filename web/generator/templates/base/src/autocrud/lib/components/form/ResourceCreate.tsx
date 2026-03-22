import { useRef, useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import { Container, Title, Stack, Button, Group, Paper, Tabs } from '@mantine/core';
import { notifications } from '@mantine/notifications';
import { IconArrowLeft } from '@tabler/icons-react';
import type { ResourceConfig, CustomCreateAction, CreateConfig } from '../../resources';
import { ResourceForm, type ResourceFormHandle } from './ResourceForm';
import { useCreateResource } from '../../hooks/useCreateResource';
import { showErrorNotification, extractUniqueConflict } from '../../utils/errorNotification';

export interface ResourceCreateProps<T> extends Partial<CreateConfig> {
  config: ResourceConfig<T>;
  basePath: string;
}

/**
 * Generic resource create page.
 *
 * When the resource config contains `customCreateActions`, a tabbed
 * interface is rendered with "Standard" plus one tab per custom action.
 * When `customFormOnly` is true, the standard form tab is hidden.
 * Otherwise the standard single-form layout is used.
 *
 * Customization props (e.g. `onCancel`, `wrappedInContainer`, `showBackButton`, `title`)
 * can be passed directly as props or set via `config.createConfig`
 * (populated from `ResourceCustomizationConfig.create`). Props win when both are present.
 */
export function ResourceCreate<T extends Record<string, any>>({
  config,
  basePath,
  // ── New customization props (override config.createConfig) ──
  customFormOnly: customFormOnlyProp,
  onCancel: onCancelProp,
  wrappedInContainer: wrappedInContainerProp,
  showBackButton: showBackButtonProp,
  title: titleProp,
}: ResourceCreateProps<T>) {
  const navigate = useNavigate();
  const formRef = useRef<ResourceFormHandle | null>(null);

  // ── Merge config.createConfig with props (props win) ──
  const cc = config.createConfig ?? {};
  const customFormOnly = customFormOnlyProp ?? cc.customFormOnly ?? false;
  const cancelHandler = onCancelProp ?? cc.onCancel ?? (() => navigate({ to: basePath }));
  const wrappedInContainer = wrappedInContainerProp ?? cc.wrappedInContainer ?? true;
  const showBackButton = showBackButtonProp ?? cc.showBackButton ?? true;
  const pageTitle = titleProp ?? cc.title ?? `Create ${config.label}`;

  const hasCustomActions =
    config.customCreateActions != null && config.customCreateActions.length > 0;

  // Track which custom action is currently submitting (if any)
  const [customActionPending, setCustomActionPending] = useState<string | null>(null);

  // ── Create mutation via TanStack Query ──
  const { createAsync, isPending } = useCreateResource<T>(config, {
    onError: (error) => {
      const conflict = extractUniqueConflict(error);
      if (conflict && formRef.current) {
        formRef.current.setFieldError(conflict.field, `此值已被使用 (unique constraint)`);
      }
    },
  });

  const handleStandardSubmit = async (values: T) => {
    // Union resource: form wraps in { data: ... }, API expects the unwrapped union object
    const submitValues = config.isUnion ? ((values as any).data as T) : values;
    try {
      const result = await createAsync(submitValues);
      navigate({ to: `${basePath}/${result.resource_id}` });
    } catch {
      // Error notification and unique-constraint field errors are
      // handled by the useCreateResource hook's onError callback.
    }
  };

  const makeCustomActionSubmit =
    (action: CustomCreateAction) => async (values: Record<string, any>) => {
      try {
        setCustomActionPending(action.name);
        await action.apiMethod(values);
        // Show toast for background actions since there's no job tracking UI
        if (action.asyncMode === 'background') {
          notifications.show({
            title: action.label,
            message: '已提交背景任務',
            color: 'blue',
          });
        }
        // Always navigate back to the parent resource list page.
        // For async job actions, the job will appear in PendingJobsAccordion.
        navigate({ to: basePath });
      } catch (error) {
        showErrorNotification(error, `${action.label} Failed`);
      } finally {
        setCustomActionPending(null);
      }
    };

  const standardForm = (
    <Paper withBorder p="md">
      <ResourceForm
        config={config}
        onSubmit={handleStandardSubmit}
        onCancel={cancelHandler}
        submitLabel="Create"
        submitting={isPending}
        formRef={formRef}
      />
    </Paper>
  );

  // Determine the tab content based on customFormOnly + hasCustomActions
  let formContent: React.ReactNode;
  if (hasCustomActions && customFormOnly) {
    // Only custom actions — no standard form
    const actions = config.customCreateActions!;
    if (actions.length === 1) {
      // Single custom action — no tabs needed
      const action = actions[0];
      formContent = (
        <Paper withBorder p="md">
          <ResourceForm
            config={{
              ...config,
              fields: action.fields,
              zodSchema: action.zodSchema,
              maxFormDepth: undefined,
            }}
            onSubmit={makeCustomActionSubmit(action)}
            onCancel={cancelHandler}
            submitLabel={action.label}
            submitting={customActionPending === action.name}
          />
        </Paper>
      );
    } else {
      // Multiple custom actions — tabs without "Standard"
      formContent = (
        <Tabs defaultValue={actions[0].name}>
          <Tabs.List>
            {actions.map((action) => (
              <Tabs.Tab key={action.name} value={action.name}>
                {action.label}
              </Tabs.Tab>
            ))}
          </Tabs.List>
          {actions.map((action) => (
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
                  onCancel={cancelHandler}
                  submitLabel={action.label}
                  submitting={customActionPending === action.name}
                />
              </Paper>
            </Tabs.Panel>
          ))}
        </Tabs>
      );
    }
  } else if (hasCustomActions) {
    // Standard + custom actions in tabs
    formContent = (
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
                onCancel={cancelHandler}
                submitLabel={action.label}
                submitting={customActionPending === action.name}
              />
            </Paper>
          </Tabs.Panel>
        ))}
      </Tabs>
    );
  } else {
    formContent = standardForm;
  }

  const createContent = (
    <Stack gap="lg">
      <Group>
        {showBackButton && (
          <Button
            variant="subtle"
            leftSection={<IconArrowLeft size={16} />}
            onClick={cancelHandler}
          >
            Back
          </Button>
        )}
        <Title order={2}>{pageTitle}</Title>
      </Group>

      {formContent}
    </Stack>
  );

  if (!wrappedInContainer) return createContent;

  return (
    <Container size="lg" py="xl">
      {createContent}
    </Container>
  );
}
