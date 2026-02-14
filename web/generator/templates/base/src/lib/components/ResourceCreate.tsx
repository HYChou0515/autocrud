import { useNavigate } from '@tanstack/react-router';
import { Container, Title, Stack, Button, Group, Paper } from '@mantine/core';
import { IconArrowLeft } from '@tabler/icons-react';
import type { ResourceConfig } from '../resources';
import { ResourceForm } from './ResourceForm';

export interface ResourceCreateProps<T> {
  config: ResourceConfig<T>;
  basePath: string;
}

/**
 * Generic resource create page
 */
export function ResourceCreate<T extends Record<string, any>>({
  config,
  basePath,
}: ResourceCreateProps<T>) {
  const navigate = useNavigate();

  const handleSubmit = async (values: T) => {
    await config.apiClient.create(values);
    navigate({ to: basePath });
  };

  return (
    <Container size="md" py="xl">
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

        <Paper withBorder p="md">
          <ResourceForm
            config={config}
            onSubmit={handleSubmit}
            onCancel={() => navigate({ to: basePath })}
            submitLabel="Create"
          />
        </Paper>
      </Stack>
    </Container>
  );
}
