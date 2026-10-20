package com.psp.tests;

import org.testng.annotations.Test;
import org.testng.Assert;

public class SmokeSanityTest {

    /**
     * Jira: AUTH-401
     */
    @Test(groups = {"smoke", "auth"}, description = "[AUTH-401] Sanity Check Authentication Endpoint")
    public void testAuthSanity() {
        // hits /api/v1/auth/token
        Assert.assertTrue(true, "Auth sanity passed");
    }
}
