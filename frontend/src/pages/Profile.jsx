function Profile() {

  const user = JSON.parse(
    localStorage.getItem("userInfo")
  );

  return (

    <div
      style={{
        padding: "30px"
      }}
    >

      <h2>
        My Profile
      </h2>

      <hr />

      <p>
        <b>Name:</b>
        {" "}
        {user?.full_name}
      </p>

      <p>
        <b>Role:</b>
        {" "}
        {user?.role}
      </p>

      <p>
        <b>Department:</b>
        {" "}
        {user?.department}
      </p>

      <p>
        <b>Company:</b>
        {" "}
        {user?.company}
      </p>

      <p>
        <b>Email:</b>
        {" "}
        {user?.official_email}
      </p>

    </div>

  );
}

export default Profile;