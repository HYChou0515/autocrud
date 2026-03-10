import { createFileRoute, Outlet, Link, useLocation, useNavigate } from '@tanstack/react-router';
import { AppShell, NavLink, Title, Group, ScrollArea, Text } from '@mantine/core';
import { getResourceNames, getResource, isAsyncCreateJob, getAsyncCreateJobChildren } from '@/autocrud/lib/resources';
import {
  IconHome,
  IconDatabase,
  IconDatabaseExport,
  IconArrowsTransferUp,
  IconPlayerPlay,
} from '@tabler/icons-react';

export const Route = createFileRoute('/autocrud-admin')({
  component: AutoCRUDLayout,
});

function AutoCRUDLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const resourceNames = getResourceNames();

  return (
    <AppShell header={{ height: 60 }} navbar={{ width: 240, breakpoint: 'sm' }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between">
          <Group>
            <Title order={3}>⚡ AutoCRUD Admin</Title>
            <Text size="xs" c="dimmed">
              Management Console
            </Text>
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
          {resourceNames
            .filter((name) => !isAsyncCreateJob(name))
            .map((name) => {
              const config = getResource(name)!;
              const jobChildren = getAsyncCreateJobChildren(name);
              const isActive =
                location.pathname === `/autocrud-admin/${name}` ||
                location.pathname.startsWith(`/autocrud-admin/${name}/`);
              const hasActiveChild = jobChildren.some(
                (jn) =>
                  location.pathname === `/autocrud-admin/${jn}` ||
                  location.pathname.startsWith(`/autocrud-admin/${jn}/`),
              );

              if (jobChildren.length > 0) {
                return (
                  <NavLink
                    key={name}
                    label={config.label}
                    leftSection={<IconDatabase size={16} />}
                    active={isActive}
                    defaultOpened={isActive || hasActiveChild}
                    onClick={() => navigate({ to: `/autocrud-admin/${name}` })}
                  >
                    {jobChildren.map((jn) => {
                      const jConfig = getResource(jn)!;
                      return (
                        <NavLink
                          key={jn}
                          component={Link}
                          to={`/autocrud-admin/${jn}`}
                          label={jConfig.label}
                          leftSection={<IconPlayerPlay size={14} />}
                          active={
                            location.pathname === `/autocrud-admin/${jn}` ||
                            location.pathname.startsWith(`/autocrud-admin/${jn}/`)
                          }
                        />
                      );
                    })}
                  </NavLink>
                );
              }

              return (
                <NavLink
                  key={name}
                  component={Link}
                  to={`/autocrud-admin/${name}`}
                  label={config.label}
                  leftSection={<IconDatabase size={16} />}
                  active={isActive}
                />
              );
            })}
        </AppShell.Section>
        <AppShell.Section>
          <Text size="xs" fw={500} c="dimmed" px="sm" py="xs">
            System
          </Text>
          <NavLink
            component={Link}
            to="/autocrud-admin/backup"
            label="Backup & Restore"
            leftSection={<IconDatabaseExport size={16} />}
            active={location.pathname.startsWith('/autocrud-admin/backup')}
          />
          <NavLink
            component={Link}
            to="/autocrud-admin/migrate"
            label="Schema Migration"
            leftSection={<IconArrowsTransferUp size={16} />}
            active={location.pathname.startsWith('/autocrud-admin/migrate')}
          />
        </AppShell.Section>
      </AppShell.Navbar>

      <AppShell.Main>
        <Outlet />
      </AppShell.Main>
    </AppShell>
  );
}
