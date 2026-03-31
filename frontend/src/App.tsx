/**
 * App — root router.
 *
 * Public routes (/login, /register, /join/:inviteCode) are accessible without auth.
 * All other routes are wrapped in <Layout>, which redirects to /login if there
 * is no token.
 *
 * Heavy pages are lazy-loaded to reduce the initial bundle size.
 */

import { lazy, Suspense, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "./components/Toaster";
import { PageSkeleton } from "./components/Skeleton";
import { Layout } from "./components/Layout";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Welcome } from "./pages/Welcome";
import { Leagues } from "./pages/Leagues";
import { Dashboard } from "./pages/Dashboard";
import { ForgotPassword } from "./pages/ForgotPassword";
import { ResetPassword } from "./pages/ResetPassword";
import { JoinLeague } from "./pages/JoinLeague";
import { BillingSuccess } from "./pages/BillingSuccess";
import { BillingCanceled } from "./pages/BillingCanceled";
import { PrivacyPolicy } from "./pages/PrivacyPolicy";
import { TermsOfService } from "./pages/TermsOfService";
import { NotFound } from "./pages/NotFound";

// Lazy-loaded pages — fetched on first navigation to reduce initial bundle
const MakePick = lazy(() => import("./pages/MakePick").then(m => ({ default: m.MakePick })));
const MyPicks = lazy(() => import("./pages/MyPicks").then(m => ({ default: m.MyPicks })));
const Leaderboard = lazy(() => import("./pages/Leaderboard").then(m => ({ default: m.Leaderboard })));
const ManageLeague = lazy(() => import("./pages/ManageLeague").then(m => ({ default: m.ManageLeague })));
const CreateLeague = lazy(() => import("./pages/CreateLeague").then(m => ({ default: m.CreateLeague })));
const TournamentDetail = lazy(() => import("./pages/TournamentDetail").then(m => ({ default: m.TournamentDetail })));
const PlayoffBracket = lazy(() => import("./pages/PlayoffBracket").then(m => ({ default: m.PlayoffBracket })));
const LeagueRules = lazy(() => import("./pages/LeagueRules").then(m => ({ default: m.LeagueRules })));
const PlatformAdmin = lazy(() => import("./pages/PlatformAdmin").then(m => ({ default: m.PlatformAdmin })));
const Settings = lazy(() => import("./pages/Settings").then(m => ({ default: m.Settings })));
const Roster = lazy(() => import("./pages/Roster").then(m => ({ default: m.Roster })));

function PageFallback() {
  return <PageSkeleton />;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <>
    <ScrollToTop />
    <Routes>
      {/* Public */}
      <Route path="/" element={<Welcome />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route path="/join/:inviteCode" element={<JoinLeague />} />
      <Route path="/billing/success" element={<BillingSuccess />} />
      <Route path="/billing/canceled" element={<BillingCanceled />} />
      <Route path="/privacy" element={<PrivacyPolicy />} />
      <Route path="/terms" element={<TermsOfService />} />

      {/* Auth-guarded — all share the Layout shell */}
      <Route element={<Layout />}>
        <Route path="/leagues" element={<Leagues />} />
        <Route path="/leagues/new" element={<Suspense fallback={<PageFallback />}><CreateLeague /></Suspense>} />
        <Route path="/leagues/:leagueId" element={<Dashboard />} />
        <Route path="/leagues/:leagueId/pick" element={<Suspense fallback={<PageFallback />}><MakePick /></Suspense>} />
        <Route path="/leagues/:leagueId/picks" element={<Suspense fallback={<PageFallback />}><MyPicks /></Suspense>} />
        <Route path="/leagues/:leagueId/tournaments/:tournamentId" element={<Suspense fallback={<PageFallback />}><TournamentDetail /></Suspense>} />
        <Route path="/leagues/:leagueId/roster" element={<Suspense fallback={<PageFallback />}><Roster /></Suspense>} />
        <Route path="/leagues/:leagueId/leaderboard" element={<Suspense fallback={<PageFallback />}><Leaderboard /></Suspense>} />
        <Route path="/leagues/:leagueId/manage" element={<Suspense fallback={<PageFallback />}><ManageLeague /></Suspense>} />
        <Route path="/leagues/:leagueId/playoff" element={<Suspense fallback={<PageFallback />}><PlayoffBracket /></Suspense>} />
        <Route path="/leagues/:leagueId/rules" element={<Suspense fallback={<PageFallback />}><LeagueRules /></Suspense>} />
        <Route path="/admin" element={<Suspense fallback={<PageFallback />}><PlatformAdmin /></Suspense>} />
        <Route path="/settings" element={<Suspense fallback={<PageFallback />}><Settings /></Suspense>} />
      </Route>

      {/* Unknown routes */}
      <Route path="*" element={<NotFound />} />
    </Routes>
    <Toaster />
    </>
  );
}
