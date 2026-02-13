import { useEffect, useState } from 'react';
import { Link } from '@tanstack/react-router';
import {
  SimpleGrid, Card, Text, Title, Group, Badge, Stack, Container, Loader,
} from '@mantine/core';
import { IconDatabase } from '@tabler/icons-react';
import { getResourceNames, getResource } from '../resources';

interface ResourceSummary {
  name: string;
  label: string;
  count: number;
  loading: boolean;
}

/**
 * Generic dashboard showing all resources with counts
 */
export function Dashboard() {
  const resourceNames = getResourceNames();
  const [summaries, setSummaries] = useState<ResourceSummary[]>(
    resourceNames.map(name => {
      const config = getResource(name)!;
      return { name, label: config.label, count: 0, loading: true };
    })
  );

  useEffect(() => {
    Promise.allSettled(
      resourceNames.map(async (name) => {
        const config = getResource(name)!;
        const res = await config.apiClient.count();
        return { name, label: config.label, count: res.data, loading: false } as ResourceSummary;
      })
    ).then((results) =>
      setSummaries(
        results.map((r, i) =>
          r.status === 'fulfilled'
            ? r.value
            : { name: resourceNames[i], label: getResource(resourceNames[i])!.label, count: 0, loading: false }
        )
      )
    );
  }, []);

  return (
    <Container size="lg" py="xl">
      <Stack gap="lg">
        <Title order={2}>Dashboard</Title>
        <Text c="dimmed">AutoCRUD Resource Overview</Text>

        <SimpleGrid cols={{ base: 1, sm: 2, md: 3 }} spacing="lg">
          {summaries.map((s) => (
            <Card
              key={s.name}
              shadow="sm"
              padding="lg"
              radius="md"
              withBorder
              component={Link}
              to={`/autocrud-admin/${s.name}`}
              style={{ textDecoration: 'none', cursor: 'pointer' }}
            >
              <Group justify="space-between" mb="xs">
                <Text fw={500}>{s.label}</Text>
                <IconDatabase size={20} />
              </Group>
              <Group>
                {s.loading ? (
                  <Loader size="sm" />
                ) : (
                  <Badge size="lg" variant="light">
                    {s.count} resources
                  </Badge>
                )}
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      </Stack>
    </Container>
  );
}
