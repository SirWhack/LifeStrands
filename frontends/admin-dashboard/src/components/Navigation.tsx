import React from 'react';
import { AppBar, Toolbar, Typography, Button, Box } from '@mui/material';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import DashboardIcon from '@mui/icons-material/Dashboard';
import BarChartIcon from '@mui/icons-material/BarChart';
import NotificationsIcon from '@mui/icons-material/Notifications';
import CloudIcon from '@mui/icons-material/Cloud';

const Navigation: React.FC = () => {
  const location = useLocation();

  return (
    <AppBar position="static">
      <Toolbar>
        <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
          Life Strands Admin
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            color="inherit"
            component={RouterLink}
            to="/dashboard"
            startIcon={<DashboardIcon />}
            variant={location.pathname === '/dashboard' || location.pathname === '/' ? 'outlined' : 'text'}
          >
            Dashboard
          </Button>
          <Button
            color="inherit"
            component={RouterLink}
            to="/metrics"
            startIcon={<BarChartIcon />}
            variant={location.pathname === '/metrics' ? 'outlined' : 'text'}
          >
            Metrics
          </Button>
          <Button
            color="inherit"
            component={RouterLink}
            to="/alerts"
            startIcon={<NotificationsIcon />}
            variant={location.pathname === '/alerts' ? 'outlined' : 'text'}
          >
            Alerts
          </Button>
          <Button
            color="inherit"
            component={RouterLink}
            to="/services"
            startIcon={<CloudIcon />}
            variant={location.pathname === '/services' ? 'outlined' : 'text'}
          >
            Services
          </Button>
        </Box>
      </Toolbar>
    </AppBar>
  );
};

export default Navigation;