import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { AppShell, NavLink, Title, Group, ScrollArea, Text } from '@mantine/core';
import { IconHome, IconDatabase } from '@tabler/icons-react';
import { getResourceNames, getResource } from '../lib/resources';

export const Route = createFileRoute('/autocrud-admin')({
  component: AutoCRUDLayout,
});

function AutoCRUDLayout() {
  const location = useLocation();
  const resourceNames = getResourceNames();

  return (
    <AppShell
      header={{ height: 60 }}
      navbar={{ width: 240, breakpoint: 'sm' }}
      padding="md"
    >
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Title order={3}>⚡ AutoCRUD Admin</Title>
            <Text size="xs" c="dimmed">Management Console</Text>
          </Group>
        </Group>
      </AppShell.Header>

      <AppShell.Navbar p="xs">
        <AppShell.Section>
          <NavLink
            component={Link}
            to="/autocrud-admin"
            label="Dashboard"
            leftSection={<IconHome size={18} />}
            active={location.pathname === '/autocrud-admin'}
          />
        </AppShell.Section>
        <AppShell.Section grow component={ScrollArea}>
          <Text size="xs" fw={500} c="dimmed" px="sm" py="xs">
            Resources
          </Text>
          {resourceNames.map((name) => {
            const config = getResource(name)!;
            return (
              <NavLink
                key={name}
                component={Link}
                to={`/autocrud-admin/${name}`}
                label={config.label}
                leftSection={<IconDatabase size={16} />}
                active={location.pathname.startsWith(`/autocrud-admin/${name}`)}
              />
            );
          })}
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
